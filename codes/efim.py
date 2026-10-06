from __future__ import annotations

import argparse
import functools
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, TextIO, Tuple

try:
    import psutil
except ImportError:
    psutil = None


class MemoryLogger:
    _instance: Optional["MemoryLogger"] = None

    def __init__(self) -> None:
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
            current_memory = process.memory_info().rss / 1024.0 / 1024.0
        else:
            current_memory = 0.0

        if current_memory > self.max_memory:
            self.max_memory = current_memory

        return current_memory

    def check_memory(self) -> float:
        return self.checkMemory()

    def getMaxMemory(self) -> float:
        return self.max_memory

    def get_max_memory(self) -> float:
        return self.getMaxMemory()


@dataclass(slots=True)
class Transaction:
    items: List[int]
    utilities: List[int]
    transactionUtility: int
    offset: int = 0
    prefixUtility: int = 0

    @classmethod
    def projected(cls, transaction: "Transaction", offsetE: int) -> "Transaction":
        utility_e = transaction.utilities[offsetE]
        prefix_utility = transaction.prefixUtility + utility_e
        transaction_utility = transaction.transactionUtility - utility_e

        for i in range(transaction.offset, offsetE):
            transaction_utility -= transaction.utilities[i]

        return cls(
            items=transaction.items,
            utilities=transaction.utilities,
            transactionUtility=transaction_utility,
            offset=offsetE + 1,
            prefixUtility=prefix_utility,
        )

    def getItems(self) -> List[int]:
        return self.items

    def getUtilities(self) -> List[int]:
        return self.utilities

    def getLastPosition(self) -> int:
        return len(self.items) - 1

    def removeUnpromisingItems(self, oldNamesToNewNames: List[int]) -> None:
        new_items: List[int] = []
        new_utilities: List[int] = []

        for item, utility in zip(self.items, self.utilities):
            new_name = oldNamesToNewNames[item] if item < len(oldNamesToNewNames) else 0

            if new_name != 0:
                new_items.append(new_name)
                new_utilities.append(utility)
            else:
                self.transactionUtility -= utility

        pairs = sorted(zip(new_items, new_utilities), key=lambda pair: pair[0])
        self.items = [item for item, _ in pairs]
        self.utilities = [utility for _, utility in pairs]
        self.offset = 0


class Dataset:
    def __init__(self, datasetPath: str, maximumTransactionCount: Optional[int] = None):
        self.transactions: List[Transaction] = []
        self.maxItem = 0

        count = 0
        with open(datasetPath, "r", encoding="utf-8", errors="replace") as file:
            for line in file:
                line = line.strip()

                if not line or line.startswith(("#", "%", "@")):
                    continue

                self.transactions.append(self._createTransaction(line))
                count += 1

                if maximumTransactionCount is not None and count >= maximumTransactionCount:
                    break

    def _createTransaction(self, line: str) -> Transaction:
        parts = line.split(":")
        if len(parts) < 3:
            raise ValueError(f"Invalid SPMF utility format: {line[:120]}")

        transaction_utility = int(float(parts[1]))
        items = [int(x) for x in parts[0].split()]
        utilities = [int(float(x)) for x in parts[2].split()]

        if len(items) != len(utilities):
            raise ValueError(
                f"Item/utility length mismatch: {len(items)} items, {len(utilities)} utilities."
            )

        if items:
            self.maxItem = max(self.maxItem, max(items))

        return Transaction(items, utilities, transaction_utility)

    def getTransactions(self) -> List[Transaction]:
        return self.transactions

    def getMaxItem(self) -> int:
        return self.maxItem


@dataclass(slots=True)
class Itemset:
    itemset: List[int]
    utility: int


class Itemsets:
    def __init__(self, name: str):
        self.name = name
        self.levels: List[List[Itemset]] = [[]]
        self.itemsetsCount = 0

    def addItemset(self, itemset: Itemset, k: int) -> None:
        while len(self.levels) <= k:
            self.levels.append([])
        self.levels[k].append(itemset)
        self.itemsetsCount += 1

    def getItemsetsCount(self) -> int:
        return self.itemsetsCount


class AlgoEFIM:
    MAXIMUM_SIZE_MERGING = 1000

    def __init__(self) -> None:
        self.highUtilityItemsets: Optional[Itemsets] = None
        self.writer: Optional[TextIO] = None
        self.patternCount = 0
        self.startTimestamp = 0.0
        self.endTimestamp = 0.0
        self.minUtil = 0

        self.utilityBinArraySU: List[int] = []
        self.utilityBinArrayLU: List[int] = []
        self.temp: List[int] = [0] * 500

        self.timeIntersections = 0.0
        self.timeDatabaseReduction = 0.0
        self.timeIdentifyPromisingItems = 0.0
        self.timeSort = 0.0
        self.timeBinarySearch = 0.0

        self.oldNameToNewNames: List[int] = []
        self.newNamesToOldNames: List[int] = []
        self.newItemCount = 0

        self.activateTransactionMerging = True
        self.activateSubtreeUtilityPruning = True

        self.transactionReadingCount = 0
        self.mergeCount = 0
        self.candidateCount = 0

    def runAlgorithm(
        self,
        minUtil: int,
        inputPath: str,
        outputPath: Optional[str],
        activateTransactionMerging: bool = True,
        maximumTransactionCount: Optional[int] = None,
        activateSubtreeUtilityPruning: bool = True,
    ) -> Optional[Itemsets]:
        return self.run_algorithm(
            min_utility=minUtil,
            input_path=inputPath,
            output_path=outputPath,
            activate_transaction_merging=activateTransactionMerging,
            maximum_transaction_count=maximumTransactionCount,
            activate_subtree_utility_pruning=activateSubtreeUtilityPruning,
        )

    def run_algorithm(
        self,
        min_utility: int,
        input_path: str,
        output_path: Optional[str],
        activate_transaction_merging: bool = True,
        maximum_transaction_count: Optional[int] = None,
        activate_subtree_utility_pruning: bool = True,
        write_output: bool = True,
    ) -> Optional[Itemsets]:
        self.mergeCount = 0
        self.transactionReadingCount = 0
        self.timeIntersections = 0.0
        self.timeDatabaseReduction = 0.0
        self.timeIdentifyPromisingItems = 0.0
        self.timeSort = 0.0
        self.timeBinarySearch = 0.0
        self.candidateCount = 0

        self.activateTransactionMerging = activate_transaction_merging
        self.activateSubtreeUtilityPruning = activate_subtree_utility_pruning
        self.startTimestamp = time.time()

        dataset = Dataset(input_path, maximum_transaction_count)
        self.minUtil = min_utility
        self.patternCount = 0

        MemoryLogger.getInstance().reset()

        output_handle: Optional[TextIO] = None
        try:
            if output_path is not None and write_output:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                output_handle = open(output_path, "w", encoding="utf-8")
                self.writer = output_handle
                self.highUtilityItemsets = None
            else:
                self.writer = None
                self.highUtilityItemsets = Itemsets("Itemsets")

            self.useUtilityBinArrayToCalculateLocalUtilityFirstTime(dataset)

            itemsToKeep = [
                item for item in range(1, len(self.utilityBinArrayLU))
                if self.utilityBinArrayLU[item] >= min_utility
            ]
            self.insertionSort(itemsToKeep, self.utilityBinArrayLU)

            self.oldNameToNewNames = [0] * (dataset.getMaxItem() + 1)
            self.newNamesToOldNames = [0] * (dataset.getMaxItem() + 1)

            current_name = 1
            for idx, old_item in enumerate(itemsToKeep):
                self.oldNameToNewNames[old_item] = current_name
                self.newNamesToOldNames[current_name] = old_item
                itemsToKeep[idx] = current_name
                current_name += 1

            self.newItemCount = len(itemsToKeep)
            self.utilityBinArraySU = [0] * (self.newItemCount + 1)

            for transaction in dataset.getTransactions():
                transaction.removeUnpromisingItems(self.oldNameToNewNames)

            sort_start = time.time()

            if self.activateTransactionMerging:
                dataset.transactions.sort(key=functools.cmp_to_key(self._compare_transactions_backward))
                empty_count = 0
                for transaction in dataset.transactions:
                    if len(transaction.items) == 0:
                        empty_count += 1
                    else:
                        break
                if empty_count:
                    dataset.transactions = dataset.transactions[empty_count:]

            self.timeSort = (time.time() - sort_start) * 1000.0

            self.useUtilityBinArrayToCalculateSubtreeUtilityFirstTime(dataset)

            itemsToExplore: List[int] = []
            if self.activateSubtreeUtilityPruning:
                for item in itemsToKeep:
                    if self.utilityBinArraySU[item] >= min_utility:
                        itemsToExplore.append(item)

            if self.activateSubtreeUtilityPruning:
                self.backtrackingEFIM(dataset.getTransactions(), itemsToKeep, itemsToExplore, 0)
            else:
                self.backtrackingEFIM(dataset.getTransactions(), itemsToKeep, itemsToKeep, 0)

            self.endTimestamp = time.time()
            MemoryLogger.getInstance().checkMemory()

        finally:
            if output_handle is not None:
                output_handle.close()
            self.writer = None

        return self.highUtilityItemsets

    @staticmethod
    def insertionSort(items: List[int], utilityBinArrayTWU: List[int]) -> None:
        items.sort(key=lambda item: (utilityBinArrayTWU[item], item))

    def _compare_transactions_backward(self, t1: Transaction, t2: Transaction) -> int:
        pos1 = len(t1.items) - 1
        pos2 = len(t2.items) - 1

        if len(t1.items) < len(t2.items):
            while pos1 >= 0:
                subtraction = t2.items[pos2] - t1.items[pos1]
                if subtraction != 0:
                    return subtraction
                pos1 -= 1
                pos2 -= 1
            return -1

        if len(t1.items) > len(t2.items):
            while pos2 >= 0:
                subtraction = t2.items[pos2] - t1.items[pos1]
                if subtraction != 0:
                    return subtraction
                pos1 -= 1
                pos2 -= 1
            return 1

        while pos2 >= 0:
            subtraction = t2.items[pos2] - t1.items[pos1]
            if subtraction != 0:
                return subtraction
            pos1 -= 1
            pos2 -= 1
        return 0

    def backtrackingEFIM(
        self,
        transactionsOfP: List[Transaction],
        itemsToKeep: List[int],
        itemsToExplore: List[int],
        prefixLength: int,
    ) -> None:
        self.candidateCount += len(itemsToExplore)

        if prefixLength >= len(self.temp):
            self.temp.extend([0] * len(self.temp))

        for j, e in enumerate(itemsToExplore):
            transactionsPe: List[Transaction] = []
            utilityPe = 0
            previousTransaction: Optional[Transaction] = None
            consecutiveMergeCount = 0

            intersection_start = time.time()

            for transaction in transactionsOfP:
                self.transactionReadingCount += 1

                binary_start = time.time()
                positionE = -1
                low = transaction.offset
                high = len(transaction.items) - 1

                while high >= low:
                    middle = (low + high) >> 1
                    middle_item = transaction.items[middle]

                    if middle_item < e:
                        low = middle + 1
                    elif middle_item == e:
                        positionE = middle
                        break
                    else:
                        high = middle - 1

                self.timeBinarySearch += (time.time() - binary_start) * 1000.0

                if positionE > -1:
                    if transaction.getLastPosition() == positionE:
                        utilityPe += transaction.utilities[positionE] + transaction.prefixUtility
                    else:
                        if (
                            self.activateTransactionMerging
                            and self.MAXIMUM_SIZE_MERGING >= (len(transaction.items) - positionE)
                        ):
                            projectedTransaction = Transaction.projected(transaction, positionE)
                            utilityPe += projectedTransaction.prefixUtility

                            if previousTransaction is None:
                                previousTransaction = projectedTransaction
                            elif self.isEqualTo(projectedTransaction, previousTransaction):
                                self.mergeCount += 1

                                if consecutiveMergeCount == 0:
                                    items = previousTransaction.items[previousTransaction.offset:].copy()
                                    utilities = previousTransaction.utilities[previousTransaction.offset:].copy()

                                    position_previous = 0
                                    position_projection = projectedTransaction.offset

                                    while position_previous < len(items):
                                        utilities[position_previous] += projectedTransaction.utilities[position_projection]
                                        position_previous += 1
                                        position_projection += 1

                                    sum_utilities = previousTransaction.prefixUtility + projectedTransaction.prefixUtility

                                    previousTransaction = Transaction(
                                        items=items,
                                        utilities=utilities,
                                        transactionUtility=previousTransaction.transactionUtility
                                        + projectedTransaction.transactionUtility,
                                        offset=0,
                                        prefixUtility=sum_utilities,
                                    )
                                else:
                                    position_previous = 0
                                    position_projected = projectedTransaction.offset

                                    while position_previous < len(previousTransaction.items):
                                        previousTransaction.utilities[position_previous] += projectedTransaction.utilities[position_projected]
                                        position_previous += 1
                                        position_projected += 1

                                    previousTransaction.transactionUtility += projectedTransaction.transactionUtility
                                    previousTransaction.prefixUtility += projectedTransaction.prefixUtility

                                consecutiveMergeCount += 1
                            else:
                                transactionsPe.append(previousTransaction)
                                previousTransaction = projectedTransaction
                                consecutiveMergeCount = 0
                        else:
                            projectedTransaction = Transaction.projected(transaction, positionE)
                            utilityPe += projectedTransaction.prefixUtility
                            transactionsPe.append(projectedTransaction)

                    transaction.offset = positionE
                else:
                    transaction.offset = low

            self.timeIntersections += (time.time() - intersection_start) * 1000.0

            if previousTransaction is not None:
                transactionsPe.append(previousTransaction)

            self.temp[prefixLength] = self.newNamesToOldNames[e]

            if utilityPe >= self.minUtil:
                self.output(prefixLength, utilityPe)

            self.useUtilityBinArraysToCalculateUpperBounds(transactionsPe, j, itemsToKeep)

            identify_start = time.time()

            newItemsToKeep: List[int] = []
            newItemsToExplore: List[int] = []

            for k in range(j + 1, len(itemsToKeep)):
                itemk = itemsToKeep[k]

                if self.utilityBinArraySU[itemk] >= self.minUtil:
                    if self.activateSubtreeUtilityPruning:
                        newItemsToExplore.append(itemk)
                    newItemsToKeep.append(itemk)
                elif self.utilityBinArrayLU[itemk] >= self.minUtil:
                    newItemsToKeep.append(itemk)

            self.timeIdentifyPromisingItems += (time.time() - identify_start) * 1000.0

            if self.activateSubtreeUtilityPruning:
                self.backtrackingEFIM(transactionsPe, newItemsToKeep, newItemsToExplore, prefixLength + 1)
            else:
                self.backtrackingEFIM(transactionsPe, newItemsToKeep, newItemsToKeep, prefixLength + 1)

        MemoryLogger.getInstance().checkMemory()

    def isEqualTo(self, t1: Transaction, t2: Transaction) -> bool:
        length1 = len(t1.items) - t1.offset
        length2 = len(t2.items) - t2.offset

        if length1 != length2:
            return False

        position1 = t1.offset
        position2 = t2.offset

        while position1 < len(t1.items):
            if t1.items[position1] != t2.items[position2]:
                return False
            position1 += 1
            position2 += 1

        return True

    def useUtilityBinArrayToCalculateLocalUtilityFirstTime(self, dataset: Dataset) -> None:
        self.utilityBinArrayLU = [0] * (dataset.getMaxItem() + 1)

        for transaction in dataset.getTransactions():
            for item in transaction.getItems():
                self.utilityBinArrayLU[item] += transaction.transactionUtility

    def useUtilityBinArrayToCalculateSubtreeUtilityFirstTime(self, dataset: Dataset) -> None:
        self.utilityBinArraySU = [0] * (self.newItemCount + 1)

        for transaction in dataset.getTransactions():
            sumSU = 0
            for i in range(len(transaction.getItems()) - 1, -1, -1):
                item = transaction.getItems()[i]
                sumSU += transaction.getUtilities()[i]
                self.utilityBinArraySU[item] += sumSU

    def useUtilityBinArraysToCalculateUpperBounds(
        self,
        transactionsPe: List[Transaction],
        j: int,
        itemsToKeep: List[int],
    ) -> None:
        initial_time = time.time()

        for i in range(j + 1, len(itemsToKeep)):
            item = itemsToKeep[i]
            self.utilityBinArraySU[item] = 0
            self.utilityBinArrayLU[item] = 0

        for transaction in transactionsPe:
            self.transactionReadingCount += 1
            sumRemainingUtility = 0
            high = len(itemsToKeep) - 1

            for i in range(len(transaction.getItems()) - 1, transaction.offset - 1, -1):
                item = transaction.getItems()[i]
                contains = False
                low = 0

                while high >= low:
                    middle = (low + high) >> 1
                    itemMiddle = itemsToKeep[middle]

                    if itemMiddle == item:
                        contains = True
                        break
                    elif itemMiddle < item:
                        low = middle + 1
                    else:
                        high = middle - 1

                if contains:
                    sumRemainingUtility += transaction.getUtilities()[i]
                    self.utilityBinArraySU[item] += sumRemainingUtility + transaction.prefixUtility
                    self.utilityBinArrayLU[item] += transaction.transactionUtility + transaction.prefixUtility

        self.timeDatabaseReduction += (time.time() - initial_time) * 1000.0

    def output(self, tempPosition: int, utility: int) -> None:
        self.patternCount += 1

        if self.writer is None:
            if self.highUtilityItemsets is not None:
                copy = self.temp[:tempPosition + 1]
                self.highUtilityItemsets.addItemset(Itemset(copy, utility), len(copy))
            return

        buffer = " ".join(str(self.temp[i]) for i in range(tempPosition + 1))
        self.writer.write(f"{buffer} #UTIL: {utility}\n")

    def printStats(self) -> None:
        print("========== EFIM v97 - STATS ============")
        print(f" minUtil = {self.minUtil}")
        print(f" High utility itemsets count: {self.patternCount}")
        print(f" Total time ~: {int((self.endTimestamp - self.startTimestamp) * 1000)} ms")
        print(f" Max memory:{MemoryLogger.getInstance().getMaxMemory()}")
        print(f" Candidate count : {self.candidateCount}")
        print("=====================================")

    def print_stats(self) -> None:
        self.printStats()


def count_output_patterns(path: str) -> int:
    p = Path(path)
    if not p.exists():
        return 0
    with p.open("r", encoding="utf-8", errors="replace") as file:
        return sum(1 for line in file if line.strip())


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
        default=str(script_dir / "output_efim.txt")
    )
    parser.add_argument("min_utility", nargs="?", type=int, default=30)
    parser.add_argument("--max-transactions", type=int, default=None)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--no-merge", action="store_true")
    parser.add_argument("--no-subtree-pruning", action="store_true")
    args = parser.parse_args()

    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))

    algo = AlgoEFIM()
    algo.run_algorithm(
        min_utility=args.min_utility,
        input_path=args.input,
        output_path=None if args.no_output else args.output,
        activate_transaction_merging=not args.no_merge,
        maximum_transaction_count=args.max_transactions,
        activate_subtree_utility_pruning=not args.no_subtree_pruning,
        write_output=not args.no_output,
    )
    algo.printStats()


if __name__ == "__main__":
    main()
