import time
import psutil
import os
import urllib.parse
from collections import defaultdict

class MemoryLogger:
    _instance = None

    @staticmethod
    def get_instance():
        if MemoryLogger._instance is None:
            MemoryLogger._instance = MemoryLogger()
        return MemoryLogger._instance

    def __init__(self):
        if MemoryLogger._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            MemoryLogger._instance = self

        self.max_memory = 0.0
        self.recording_mode = False
        self.output_file = None
        self.writer = None

    def get_max_memory(self):
        return self.max_memory

    def reset(self):
        self.max_memory = 0.0

    def check_memory(self):
        process = psutil.Process(os.getpid())
        current_memory = process.memory_info().rss / 1024 / 1024
        if current_memory > self.max_memory:
            self.max_memory = current_memory

        if self.recording_mode:
            try:
                self.writer.write(f"{current_memory}\n")
            except IOError as e:
                print(e)

        return current_memory

    def start_recording_mode(self, file_name):
        self.recording_mode = True
        self.output_file = file_name
        try:
            self.writer = open(self.output_file, 'w')
        except IOError as e:
            print(e)

    def stop_recording_mode(self):
        if self.recording_mode:
            try:
                self.writer.close()
            except IOError as e:
                print(e)
            self.recording_mode = False

class ItemNameConverter:
    def __init__(self, item_count):
        self.new_names_to_old_names = [None] * (item_count + 1)
        self.old_names_to_new_names = {}
        self.current_index = 1

    def assign_new_name(self, old_name):
        new_name = self.current_index
        self.old_names_to_new_names[old_name] = new_name
        self.new_names_to_old_names[new_name] = old_name
        self.current_index += 1
        return new_name

    def to_new_name(self, old_name):
        return self.old_names_to_new_names.get(old_name)

    def to_old_name(self, new_name):
        if new_name >= len(self.new_names_to_old_names):
            return None
        return self.new_names_to_old_names[new_name]

class Cell:
    def __init__(self, item=None, utility=None):
        self.item = item
        self.utility = utility

    def __str__(self):
        return f"({self.item}, {self.utility})"

class Pointer:
    def __init__(self, prefix_utility, pos):
        self.prefix_utility = prefix_utility
        self.pos = pos

class Row:
    def __init__(self, item):
        self.item = item
        self.support = 0
        self.utility = 0
        self.ltwu = 0
        self.rutil = 0
        self.pointers = []

    def __str__(self):
        pointers_str = ', '.join(str(pointer) for pointer in self.pointers)
        return f"{self.item} s:{self.support} u:{self.utility} ubItem:{self.ltwu} ubPFE:{self.rutil} pointers: [{pointers_str}]"

class AlgoD2HUP:
    BUFFERS_SIZE = 200

    def __init__(self):
        self.startTimestamp = 0
        self.endTimestamp = 0
        self.huiCount = 0
        self.case1count = 0
        self.case2count = 0
        self.writer = None
        self.itemsetBuffer = None
        self.DEBUG = True
        self.cells = None
        self.minUtility = 0
        self.mapItemRow = None
        self.nameConverter = None

    def runAlgorithm(self, input_file, output_file, minUtility):
        # Reset memory logger
        MemoryLogger.get_instance().reset()

        self.itemsetBuffer = [0] * self.BUFFERS_SIZE

        self.startTimestamp = time.time()

        self.writer = open(output_file, 'w')

        self.minUtility = minUtility

        mapItemToTWU = {}
        self.case1count = 0
        self.case2count = 0

        itemOccurrencesCount = 0
        transactionCount = 0

        with open(input_file, 'r') as f:
            for line in f:
                if line.strip() == '' or line[0] in '#%@':
                    continue

                parts = line.split(':')
                if len(parts) != 3:
                    continue

                items = list(map(int, parts[0].strip().split()))
                transactionUtility = int(parts[1].strip())
                utilities = list(map(int, parts[2].strip().split()))

                for item in items:
                    if item not in mapItemToTWU:
                        mapItemToTWU[item] = 0
                    mapItemToTWU[item] += transactionUtility
                    itemOccurrencesCount += 1

                transactionCount += 1

        rowList = []
        self.mapItemRow = {}
        self.cells = [None] * (transactionCount + itemOccurrencesCount)

        for item, twu in mapItemToTWU.items():
            if twu >= minUtility:
                row = Row(item)
                row.ltwu = twu
                rowList.append(row)
                self.mapItemRow[item] = row

        rowList.sort(key=lambda row: mapItemToTWU[row.item])

        self.nameConverter = ItemNameConverter(len(rowList))

        for row in rowList:
            row.item = self.nameConverter.assign_new_name(row.item)

        currentCellIndex = 0
        with open(input_file, 'r') as f:
            for line in f:
                if line.strip() == '' or line[0] in '#%@':
                    continue

                parts = line.strip().split(':')
                if len(parts) != 3:
                    continue

                items = list(map(int, parts[0].split()))
                utilities = list(map(int, parts[2].split()))

                remainingUtility = 0
                transactionBegin = currentCellIndex

                # D2HUP suffix processing assumes that every transaction
                # follows the internal item order established by the TWU-
                # based renaming above.  Preserve each item/utility pair
                # and sort by the renamed item ID before creating cells.
                revisedTransaction = []

                for i in range(len(items)):
                    item = items[i]
                    if mapItemToTWU[item] >= minUtility:
                        revisedTransaction.append(
                            (
                                self.nameConverter.to_new_name(item),
                                utilities[i]
                            )
                        )

                revisedTransaction.sort(key=lambda pair: pair[0])

                for new_item, utility in revisedTransaction:
                    cell = Cell(new_item, utility)
                    self.cells[currentCellIndex] = cell
                    currentCellIndex += 1
                    remainingUtility += cell.utility

                transactionEnd = currentCellIndex - 1
                self.cells[currentCellIndex] = None
                currentCellIndex += 1

                for i in range(transactionBegin, transactionEnd + 1):
                    cell = self.cells[i]
                    row = self.mapItemRow[self.nameConverter.to_old_name(cell.item)]
                    row.support += 1
                    row.utility += cell.utility
                    remainingUtility -= cell.utility
                    row.rutil += remainingUtility
                    row.pointers.append(Pointer(0, i))

        if self.DEBUG:
            print("------ INITIAL CAUL -----")
            print("The cell list:")
            for cell in self.cells:
                if cell is None:
                    print("|")
                else:
                    print(cell, end=' ')
            print("\nThe table:")
            for row in rowList:
                print(row, "[the items:", end=' ')
                for pointer in row.pointers:
                    print(self.cells[pointer.pos].item, end=' ')
                print("]")

        MemoryLogger.get_instance().check_memory()

        self.d2hup(self.itemsetBuffer, 0, rowList, transactionCount, 0)

        MemoryLogger.get_instance().check_memory()
        self.writer.close()
        self.endTimestamp = time.time()

    def d2hup(self, prefix, prefixLength, rowList, prefixSupport, prefixUtility):
        if self.DEBUG:
            print(f"prefix: {prefix[:prefixLength]}, prefixLength: {prefixLength}")

        allPromisingItemsHaveSameSupportAsPrefix = True
        allPromisingItemAreHighUtility = True

        # Check Case 1 condition
        for row in rowList:
            if row.utility < self.minUtility:
                allPromisingItemAreHighUtility = False
                break

        for row in rowList:
            if row.support != prefixSupport:
                allPromisingItemsHaveSameSupportAsPrefix = False
                break

        if allPromisingItemsHaveSameSupportAsPrefix and allPromisingItemAreHighUtility:
            # Generate all non-empty subsets of W U pat(N) and output them
            # BENCHMARK_SILENCED_DEBUG: print(f"Case 1 detected with rowList: {[row.item for row in rowList]}")
            subsets = []
            for i in range(1, 1 << len(rowList)):
                subset = []
                utility = prefixUtility
                for j in range(len(rowList)):
                    if i & (1 << j):
                        subset.append(rowList[j].item)
                        utility += rowList[j].utility
                if utility >= self.minUtility:
                    subsets.append((subset, utility))

            for subset, utility in subsets:
                newPrefixLength = prefixLength
                for item in subset:
                    prefix[newPrefixLength] = item
                    newPrefixLength += 1
                self.writeOut(prefix, newPrefixLength, utility)

            self.case1count += 1
            return

        # Check Case 2 condition
        if allPromisingItemsHaveSameSupportAsPrefix:
            delta = min(row.utility - prefixUtility for row in rowList)
            sum_util = prefixUtility + sum(row.utility - prefixUtility for row in rowList)

            if self.minUtility <= sum_util < (self.minUtility + delta):
                self.case2count += 1
                itemsetLength = prefixLength
                for row in rowList:
                    prefix[itemsetLength] = row.item
                    itemsetLength += 1
                self.writeOut(prefix, itemsetLength, sum_util)
                return

        for row in rowList:
            if row.utility >= self.minUtility:
                self.writeOut_with_item(prefix, prefixLength, row.item, row.utility)

            if row.utility + row.rutil >= self.minUtility:
                newRowList = []
                self.mapItemRow.clear()

                for pointer in row.pointers:
                    transactionBegin = pointer.pos
                    newPrefixRowUtility = pointer.prefix_utility + self.cells[pointer.pos].utility
                    transactionBegin += 1

                    if self.cells[transactionBegin] is None:
                        continue

                    transactionEnd = -1
                    rtwu = 0
                    for pos in range(transactionBegin, len(self.cells)):
                        if self.cells[pos] is None:
                            transactionEnd = pos - 1
                            break
                        rtwu += self.cells[pos].utility

                    remainingUtility = rtwu
                    for pos in range(transactionBegin, transactionEnd + 1):
                        cell = self.cells[pos]
                        rowItem = self.mapItemRow.get(cell.item)
                        if rowItem is None:
                            rowItem = Row(cell.item)
                            self.mapItemRow[cell.item] = rowItem
                        rowItem.support += 1
                        rowItem.utility += newPrefixRowUtility + cell.utility
                        rowItem.ltwu += rtwu
                        rowItem.pointers.append(Pointer(newPrefixRowUtility, pos))
                        remainingUtility -= cell.utility
                        rowItem.rutil += remainingUtility

                for rowItem in self.mapItemRow.values():
                    if row.utility + rowItem.ltwu >= self.minUtility:
                        newRowList.append(rowItem)

                newRowList.sort(key=lambda row: row.item)
                prefix[prefixLength] = row.item
                self.d2hup(prefix, prefixLength + 1, newRowList, row.support, row.utility)

        MemoryLogger.get_instance().check_memory()

    def writeOut(self, prefix, prefixLength, utility):
        self.huiCount += 1
        buffer = ' '.join(str(self.nameConverter.to_old_name(prefix[i])) for i in range(prefixLength))
        buffer += " #UTIL: " + str(utility)
        self.writer.write(buffer + '\n')

    def writeOut_with_item(self, prefix, prefixLength, item, utility):
        self.huiCount += 1
        buffer = ' '.join(str(self.nameConverter.to_old_name(prefix[i])) for i in range(prefixLength))
        buffer += ' ' + str(self.nameConverter.to_old_name(item))
        buffer += " #UTIL: " + str(utility)
        self.writer.write(buffer + '\n')

    def printStats(self):
        print("=============  D2HUP ALGORITHM v97- STATS =============")
        print(f" Case1 count: {self.case1count} | Case2 count: {self.case2count}")
        print(f" Total time ~ {int((self.endTimestamp - self.startTimestamp) * 1000)} ms")
        print(f" Max Memory ~ {MemoryLogger.get_instance().get_max_memory()} MB")
        print(f" High-utility itemsets count : {self.huiCount}")
        print("===================================================")

def main():
    input_file = file_to_path("DB_Utility.txt")
    output_file = file_to_path("output.txt")

    min_utility = 30

    algo = AlgoD2HUP()
    algo.runAlgorithm(input_file, output_file, min_utility)

    algo.printStats()

def file_to_path(filename):
    url = os.path.join(os.path.dirname(__file__), filename)
    return urllib.parse.unquote(url)

if __name__ == "__main__":
    main()





