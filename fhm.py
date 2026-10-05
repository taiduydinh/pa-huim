import sys
import psutil
import os
import time
import urllib.parse
from collections import defaultdict
from itertools import combinations

class Element:
    """
    This class represents an Element of a utility list as used by the HUI-Miner algorithm.
    """

    def __init__(self, tid, iutils, rutils):
        """
        Constructor.
        
        :param tid: the transaction id
        :param iutils: the itemset utility
        :param rutils: the remaining utility
        """
        self.tid = tid
        self.iutils = iutils
        self.rutils = rutils

class UtilityList:
    """
    This class represents a UtilityList as used by the HUI-Miner algorithm.
    """
    def __init__(self, item):
        """
        Constructor.
        
        :param item: the item that is used for this utility list
        """
        self.item = item  # the item
        self.sumIutils = 0  # the sum of item utilities
        self.sumRutils = 0  # the sum of remaining utilities
        self.elements = []  # the elements, a list of Element objects

    def add_element(self, element):
        """
        Method to add an element to this utility list and update the sums at the same time.
        
        :param element: an Element object
        """
        self.sumIutils += element.iutils
        self.sumRutils += element.rutils
        self.elements.append(element)

    def get_support(self):
        """
        Get the support of the itemset represented by this utility-list
        
        :return: the support as a number of transactions
        """
        return len(self.elements)

    def get_utils(self):
        """
        Get the sum of iutil values
        
        :return: the sum of iutil values
        """
        return self.sumIutils

class MemoryLogger:
    """
    This class is used to record the maximum memory usage of an algorithm during a given execution.
    It is implemented using the "singleton" design pattern.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MemoryLogger, cls).__new__(cls, *args, **kwargs)
            cls._instance.max_memory = 0
        return cls._instance

    def get_max_memory(self):
        """
        To get the maximum amount of memory used until now.
        
        :return: a float value indicating memory in megabytes
        """
        return self._instance.max_memory

    def reset(self):
        """
        Reset the maximum amount of memory recorded.
        """
        self._instance.max_memory = 0

    def check_memory(self):
        """
        Check the current memory usage and record it if it is higher than the amount of memory previously recorded.
        
        :return: the memory usage in megabytes
        """
        process = psutil.Process()
        current_memory = process.memory_info().rss / 1024 / 1024
        if current_memory > self._instance.max_memory:
            self._instance.max_memory = current_memory
        return current_memory

class AlgoFHM:
    def __init__(self):
        self.startTimestamp = 0
        self.endTimestamp = 0
        self.huiCount = 0
        self.candidateCount = 0
        self.mapItemToTWU = {}
        self.writer = None
        self.mapFMAP = defaultdict(lambda: defaultdict(int))
        self.ENABLE_LA_PRUNE = True
        self.DEBUG = False
        self.BUFFERS_SIZE = 200
        self.itemsetBuffer = []

    class Pair:
        def __init__(self, item=0, utility=0):
            self.item = item
            self.utility = utility

    def runAlgorithm(self, input, output, minUtility):
        MemoryLogger().reset()
        self.itemsetBuffer = [0] * self.BUFFERS_SIZE
        self.startTimestamp = time.time()
        self.writer = open(output, 'w')

        self.mapItemToTWU = defaultdict(int)
        with open(input, 'r') as file:
            for line in file:
                if line.startswith(('#', '%', '@')) or not line.strip():
                    continue
                items, transactionUtility = line.split(':')[:2]
                transactionUtility = int(transactionUtility.strip())
                items = list(map(int, items.strip().split()))
                for item in items:
                    self.mapItemToTWU[item] += transactionUtility

        listOfUtilityLists = []
        mapItemToUtilityList = {}
        for item, twu in self.mapItemToTWU.items():
            if twu >= minUtility:
                uList = UtilityList(item)
                mapItemToUtilityList[item] = uList
                listOfUtilityLists.append(uList)

        listOfUtilityLists.sort(key=lambda ul: ul.item)
        with open(input, 'r') as file:
            tid = 0
            for line in file:
                if line.startswith(('#', '%', '@')) or not line.strip():
                    continue
                parts = line.split(':')
                items = list(map(int, parts[0].strip().split()))
                transactionUtility = int(parts[1].strip())
                utilities = list(map(int, parts[2].strip().split()))

                revisedTransaction = []
                remainingUtility = 0
                for item, utility in zip(items, utilities):
                    if self.mapItemToTWU[item] >= minUtility:
                        revisedTransaction.append(self.Pair(item, utility))
                        remainingUtility += utility

                revisedTransaction.sort(key=lambda pair: pair.item)
                newTWU = sum(pair.utility for pair in revisedTransaction)
                for i in range(len(revisedTransaction)):
                    pair = revisedTransaction[i]
                    remainingUtility -= pair.utility
                    utilityListOfItem = mapItemToUtilityList[pair.item]
                    utilityListOfItem.add_element(Element(tid, pair.utility, remainingUtility))
                    mapFMAPItem = self.mapFMAP[pair.item]
                    for j in range(i + 1, len(revisedTransaction)):
                        pairAfter = revisedTransaction[j]
                        mapFMAPItem[pairAfter.item] += newTWU
                tid += 1

        MemoryLogger().check_memory()
        self.fhm(self.itemsetBuffer, 0, None, listOfUtilityLists, minUtility)
        MemoryLogger().check_memory()
        self.writer.close()
        self.endTimestamp = time.time()

    def compareItems(self, item1, item2):
        return (self.mapItemToTWU[item1] - self.mapItemToTWU[item2]) or (item1 - item2)

    def fhm(self, prefix, prefixLength, pUL, ULs, minUtility):
        for i in range(len(ULs)):
            X = ULs[i]
            if X.sumIutils >= minUtility:
                self.writeOut(prefix, prefixLength, X.item, X.sumIutils)
            if X.sumIutils + X.sumRutils >= minUtility:
                exULs = []
                for j in range(i + 1, len(ULs)):
                    Y = ULs[j]
                    mapTWUF = self.mapFMAP.get(X.item, {})
                    if mapTWUF.get(Y.item, 0) < minUtility:
                        continue
                    self.candidateCount += 1
                    temp = self.construct(pUL, X, Y, minUtility)
                    if temp:
                        exULs.append(temp)
                self.itemsetBuffer[prefixLength] = X.item
                self.fhm(self.itemsetBuffer, prefixLength + 1, X, exULs, minUtility)
        MemoryLogger().check_memory()

    def construct(self, P, px, py, minUtility):
        pxyUL = UtilityList(py.item)
        totalUtility = px.sumIutils + px.sumRutils
        for ex in px.elements:
            ey = self.findElementWithTID(py, ex.tid)
            if not ey:
                if self.ENABLE_LA_PRUNE:
                    totalUtility -= ex.iutils + ex.rutils
                    if totalUtility < minUtility:
                        return None
                continue
            if not P:
                eXY = Element(ex.tid, ex.iutils + ey.iutils, ey.rutils)
                pxyUL.add_element(eXY)
            else:
                e = self.findElementWithTID(P, ex.tid)
                if e:
                    eXY = Element(ex.tid, ex.iutils + ey.iutils - e.iutils, ey.rutils)
                    pxyUL.add_element(eXY)
        return pxyUL

    def findElementWithTID(self, ulist, tid):
        first, last = 0, len(ulist.elements) - 1
        while first <= last:
            middle = (first + last) // 2
            if ulist.elements[middle].tid < tid:
                first = middle + 1
            elif ulist.elements[middle].tid > tid:
                last = middle - 1
            else:
                return ulist.elements[middle]
        return None

    def writeOut(self, prefix, prefixLength, item, utility):
        self.huiCount += 1
        buffer = ' '.join(map(str, prefix[:prefixLength])) + f' {item} #UTIL: {utility}\n'
        self.writer.write(buffer)

    def printStats(self):
        print("=============  FHM ALGORITHM - SPMF 0.97e - STATS =============")
        print(" Total time ~ ", round((self.endTimestamp - self.startTimestamp) * 1000), "ms")
        print(f" Memory ~ {MemoryLogger().get_max_memory():.2f} MB")
        print(f" High-utility itemsets count : {self.huiCount}")
        print(f" Candidate count : {self.candidateCount}")
        if self.DEBUG:
            pairCount = sum(len(v) for v in self.mapFMAP.values())
            maxMemory = self.getObjectSize(self.mapFMAP)
            print(f"CMAP size {maxMemory:.2f} MB")
            print(f"PAIR COUNT {pairCount}")
        print("===================================================")

    def getObjectSize(self, obj):
        return sum(map(lambda x: sys.getsizeof(x) / 1024 / 1024, [obj]))

class MainTestFHM:
    @staticmethod
    def main():
        input = MainTestFHM.fileToPath("DB_Utility.txt")
        output = "output.txt"

        min_utility = 30
        
        # Applying the HUIMiner algorithm
        algo = AlgoFHM()
        algo.runAlgorithm(input, output, min_utility)
        algo.printStats()

    @staticmethod
    def fileToPath(filename):
        return urllib.parse.unquote(os.path.join(os.path.dirname(__file__), filename))

if __name__ == "__main__":
    MainTestFHM.main()


