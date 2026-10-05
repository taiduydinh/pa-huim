from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TextIO, Tuple

try:
    import psutil
except ImportError:
    psutil = None


@dataclass(slots=True)
class Element:
    tid: int
    iutils: int
    rutils: int


class UtilityList:
    __slots__ = ("item", "sumIutils", "sumRutils", "elements")

    def __init__(self, item: int):
        self.item = item
        self.sumIutils = 0
        self.sumRutils = 0
        self.elements: List[Element] = []

    def addElement(self, element: Element) -> None:
        self.sumIutils += element.iutils
        self.sumRutils += element.rutils
        self.elements.append(element)

    def add_element(self, element: Element) -> None:
        self.addElement(element)

    def getSupport(self) -> int:
        return len(self.elements)

    def getUtils(self) -> int:
        return self.sumIutils


class MemoryLogger:
    _instance: Optional["MemoryLogger"] = None

    def __init__(self):
        self.max_memory = 0.0

    @classmethod
    def getInstance(cls) -> "MemoryLogger":
        if cls._instance is None:
            cls._instance = MemoryLogger()
        return cls._instance

    @classmethod
    def get_instance(cls) -> "MemoryLogger":
        return cls.getInstance()

    def reset(self) -> None:
        self.max_memory = 0.0

    def checkMemory(self) -> float:
        if psutil is not None:
            process = psutil.Process(os.getpid())
            current = process.memory_info().rss / 1024.0 / 1024.0
        else:
            current = 0.0

        if current > self.max_memory:
            self.max_memory = current

        return current

    def check_memory(self) -> float:
        return self.checkMemory()

    def getMaxMemory(self) -> float:
        return self.max_memory

    def get_max_memory(self) -> float:
        return self.getMaxMemory()


class AlgoHUIMiner:
    BUFFERS_SIZE = 200

    def __init__(self):
        self.startTimestamp = 0.0
        self.endTimestamp = 0.0
        self.huiCount = 0
        self.joinCount = 0
        self.mapItemToTWU: Dict[int, int] = {}
        self.writer: Optional[TextIO] = None
        self.itemsetBuffer: List[int] = [0] * self.BUFFERS_SIZE
        self.write_output = True

    def runAlgorithm(self, input: str, output: str, minUtility: int) -> None:
        self.run_algorithm(input, output, minUtility)

    def run_algorithm(
        self,
        input_path: str,
        output_path: str,
        min_utility: int,
        max_transactions: Optional[int] = None,
        write_output: bool = True,
    ) -> None:
        MemoryLogger.getInstance().reset()

        self.startTimestamp = time.time()
        self.endTimestamp = 0.0
        self.huiCount = 0
        self.joinCount = 0
        self.mapItemToTWU = {}
        self.itemsetBuffer = [0] * self.BUFFERS_SIZE
        self.write_output = write_output

        self._first_database_scan(input_path, max_transactions)

        listOfUtilityLists: List[UtilityList] = []
        mapItemToUtilityList: Dict[int, UtilityList] = {}

        for item, twu in self.mapItemToTWU.items():
            if twu >= min_utility:
                utility_list = UtilityList(item)
                mapItemToUtilityList[item] = utility_list
                listOfUtilityLists.append(utility_list)

        listOfUtilityLists.sort(key=lambda utility_list: self._item_order_key(utility_list.item))

        self._second_database_scan(
            input_path=input_path,
            min_utility=min_utility,
            mapItemToUtilityList=mapItemToUtilityList,
            max_transactions=max_transactions,
        )

        MemoryLogger.getInstance().checkMemory()

        output_handle: Optional[TextIO] = None
        try:
            if write_output:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                output_handle = open(output_path, "w", encoding="utf-8")
                self.writer = output_handle
            else:
                self.writer = None

            self._hui_miner(
                prefix=self.itemsetBuffer,
                prefix_length=0,
                pUL=None,
                ULs=listOfUtilityLists,
                min_utility=min_utility,
            )

            MemoryLogger.getInstance().checkMemory()

        finally:
            if output_handle is not None:
                output_handle.close()
            self.writer = None
            self.endTimestamp = time.time()

    def _first_database_scan(
        self,
        input_path: str,
        max_transactions: Optional[int],
    ) -> None:
        for items, _, transaction_utility in _iter_spmf_utility_transactions(input_path, max_transactions):
            for item in items:
                self.mapItemToTWU[item] = self.mapItemToTWU.get(item, 0) + transaction_utility

    def _second_database_scan(
        self,
        input_path: str,
        min_utility: int,
        mapItemToUtilityList: Dict[int, UtilityList],
        max_transactions: Optional[int],
    ) -> None:
        tid = 0

        for items, utilities, _ in _iter_spmf_utility_transactions(input_path, max_transactions):
            revised_transaction: List[Tuple[int, int]] = []
            remaining_utility = 0

            for item, utility in zip(items, utilities):
                if self.mapItemToTWU.get(item, 0) >= min_utility:
                    revised_transaction.append((item, utility))
                    remaining_utility += utility

            revised_transaction.sort(key=lambda pair: self._item_order_key(pair[0]))

            for item, utility in revised_transaction:
                remaining_utility -= utility
                utility_list = mapItemToUtilityList[item]
                utility_list.addElement(Element(tid, utility, remaining_utility))

            tid += 1

    def _item_order_key(self, item: int) -> Tuple[int, int]:
        return self.mapItemToTWU[item], item

    def _hui_miner(
        self,
        prefix: List[int],
        prefix_length: int,
        pUL: Optional[UtilityList],
        ULs: List[UtilityList],
        min_utility: int,
    ) -> None:
        if prefix_length >= len(prefix):
            prefix.extend([0] * len(prefix))

        for i, X in enumerate(ULs):
            if X.sumIutils >= min_utility:
                self._write_out(prefix, prefix_length, X.item, X.sumIutils)

            if X.sumIutils + X.sumRutils >= min_utility:
                exULs: List[UtilityList] = []

                for j in range(i + 1, len(ULs)):
                    Y = ULs[j]
                    exULs.append(self._construct(pUL, X, Y))
                    self.joinCount += 1

                prefix[prefix_length] = X.item
                self._hui_miner(prefix, prefix_length + 1, X, exULs, min_utility)

        MemoryLogger.getInstance().checkMemory()

    def _construct(
        self,
        P: Optional[UtilityList],
        px: UtilityList,
        py: UtilityList,
    ) -> UtilityList:
        pxyUL = UtilityList(py.item)

        for ex in px.elements:
            ey = self._find_element_with_tid(py, ex.tid)

            if ey is None:
                continue

            if P is None:
                pxyUL.addElement(Element(ex.tid, ex.iutils + ey.iutils, ey.rutils))
            else:
                e = self._find_element_with_tid(P, ex.tid)
                if e is not None:
                    pxyUL.addElement(
                        Element(
                            ex.tid,
                            ex.iutils + ey.iutils - e.iutils,
                            ey.rutils,
                        )
                    )

        return pxyUL

    def _find_element_with_tid(
        self,
        utility_list: UtilityList,
        tid: int,
    ) -> Optional[Element]:
        elements = utility_list.elements
        first = 0
        last = len(elements) - 1

        while first <= last:
            middle = (first + last) >> 1
            middle_tid = elements[middle].tid

            if middle_tid < tid:
                first = middle + 1
            elif middle_tid > tid:
                last = middle - 1
            else:
                return elements[middle]

        return None

    def _write_out(
        self,
        prefix: List[int],
        prefix_length: int,
        item: int,
        utility: int,
    ) -> None:
        self.huiCount += 1

        if not self.write_output or self.writer is None:
            return

        if prefix_length > 0:
            items = " ".join(str(prefix[i]) for i in range(prefix_length))
            self.writer.write(f"{items} {item} #UTIL: {utility}\n")
        else:
            self.writer.write(f"{item} #UTIL: {utility}\n")

    def printStats(self) -> None:
        print("=============  HUI-MINER ALGORITHM - STATS =============")
        print(f" Total time ~ {int((self.endTimestamp - self.startTimestamp) * 1000)} ms")
        print(f" Memory ~ {MemoryLogger.getInstance().getMaxMemory():.2f} MB")
        print(f" High-utility itemsets count : {self.huiCount}")
        print(f" Join count : {self.joinCount}")
        print("===================================================")

    def print_stats(self) -> None:
        self.printStats()


def _iter_spmf_utility_transactions(
    input_path: str,
    max_transactions: Optional[int] = None,
) -> Iterable[Tuple[List[int], List[int], int]]:
    count = 0

    with open(input_path, "r", encoding="utf-8", errors="replace") as file:
        for line_no, line in enumerate(file, start=1):
            line = line.strip()

            if not line or line.startswith(("#", "%", "@")):
                continue

            parts = line.split(":")

            if len(parts) < 3:
                raise ValueError(f"Invalid SPMF utility format at line {line_no}: {line[:120]}")

            items = [int(x) for x in parts[0].split()]
            transaction_utility = int(float(parts[1]))
            utilities = [int(float(x)) for x in parts[2].split()]

            if len(items) != len(utilities):
                raise ValueError(
                    f"Item/utility length mismatch at line {line_no}: "
                    f"{len(items)} items and {len(utilities)} utilities."
                )

            yield items, utilities, transaction_utility

            count += 1
            if max_transactions is not None and count >= max_transactions:
                break


def main() -> None:
    parser = argparse.ArgumentParser()
    script_dir = Path(__file__).resolve().parent

    parser.add_argument(
        "input",
        nargs="?",
        default=str(script_dir / "DB_Utility.txt")
    )

    parser.add_argument(
        "output",
        nargs="?",
        default=str(script_dir / "output_hui_miner.txt")
    )
    parser.add_argument("min_utility", nargs="?", type=int, default=30)
    parser.add_argument("--max-transactions", type=int, default=None)
    parser.add_argument("--no-output", action="store_true")
    args = parser.parse_args()

    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))

    algo = AlgoHUIMiner()
    algo.run_algorithm(
        input_path=args.input,
        output_path=args.output,
        min_utility=args.min_utility,
        max_transactions=args.max_transactions,
        write_output=not args.no_output,
    )
    algo.printStats()


if __name__ == "__main__":
    main()
