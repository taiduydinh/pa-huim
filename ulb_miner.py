import os
import urllib.parse
import time
import collections

class MemoryLogger:
    _instance = None

    def __init__(self):
        self.max_memory = 0

    @staticmethod
    def get_instance():
        if MemoryLogger._instance is None:
            MemoryLogger._instance = MemoryLogger()
        return MemoryLogger._instance

    def reset(self):
        self.max_memory = 0

    def check_memory(self):
        # Simulate memory check (not implemented in this example)
        pass

    def get_max_memory(self):
        return self.max_memory


class Element:
    def __init__(self, tid=None, iutils=None, rutils=None):
        self.tid = tid
        self.iutils = iutils
        self.rutils = rutils


class Summary:
    def __init__(self, item=None, start_pos=0, end_pos=0, sum_iutils=0, sum_rutils=0):
        self.item = item
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.sum_iutils = sum_iutils
        self.sum_rutils = sum_rutils


class UtilityListBuffer:
    def __init__(self, sum_support=None, item_count=None):
        if sum_support and item_count:
            self.elements = [Element() for _ in range(sum_support * 2)]
            self.summaries = [Summary() for _ in range(item_count * 2)]
        else:
            self.elements = []
            self.summaries = []
        self.current_summary = None
        self.allocated_element_count_for_last_utility_list = 0

    def select_current_utility_list(self, utility_list_index):
        self.current_summary = self.summaries[utility_list_index]

    def get_sum_iutil_current_utility_list(self):
        return self.current_summary.sum_iutils

    def get_sum_rutil_current_utility_list(self):
        return self.current_summary.sum_rutils

    def get_item_current_utility_list(self):
        return self.current_summary.item

    def get_element_count_current_utility_list(self):
        return self.current_summary.end_pos - self.current_summary.start_pos

    def get_ith_element_in_current_utility_list(self, element_number):
        return self.elements[self.current_summary.start_pos + element_number]

    def create_a_new_utility_list(self, item, utility_list_index):
        if utility_list_index >= len(self.summaries):
            self.current_summary = Summary()
            self.summaries.append(self.current_summary)
        else:
            self.current_summary = self.summaries[utility_list_index]

        self.current_summary.item = item
        self.current_summary.sum_iutils = 0
        self.current_summary.sum_rutils = 0

        if utility_list_index == 0:
            self.current_summary.start_pos = 0
            self.current_summary.end_pos = 0
        else:
            previous_utility_list = self.summaries[utility_list_index - 1]
            self.current_summary.start_pos = previous_utility_list.end_pos + self.allocated_element_count_for_last_utility_list
            self.current_summary.end_pos = self.current_summary.start_pos

        self.allocated_element_count_for_last_utility_list = 0

    def add_element_to_current_utility_list(self, tid, iutil, rutil):
        insertion_position = self.current_summary.end_pos

        if insertion_position >= len(self.elements):
            self.elements.append(Element(tid, iutil, rutil))
        else:
            element = self.elements[insertion_position]
            element.tid = tid
            element.iutils = iutil
            element.rutils = rutil

        self.current_summary.sum_iutils += iutil
        self.current_summary.sum_rutils += rutil
        self.current_summary.end_pos += 1

    def allocate_space_for_elements(self, support):
        for _ in range(support):
            self.elements.append(Element())
        self.allocated_element_count_for_last_utility_list = support

    def find_element_with_tid_current_utility_list(self, tid):
        first = self.current_summary.start_pos
        last = self.current_summary.end_pos - 1

        while first <= last:
            middle = (first + last) // 2

            if self.elements[middle].tid < tid:
                first = middle + 1
            elif self.elements[middle].tid > tid:
                last = middle - 1
            else:
                return self.elements[middle]

        return None

    def finish_building_single_items_utility_lists(self):
        self.allocated_element_count_for_last_utility_list = 0

    def print_to_string(self):
        print(" ====== ELEMENTS ======")
        for element in self.elements:
            print(f"tid = {element.tid} iutil {element.iutils} rutil {element.rutils}")
        print(" ====== UTILITY-LISTS ======")
        for summary in self.summaries:
            print(f"item = {summary.item} start {summary.start_pos} end {summary.end_pos} sumI {summary.sum_iutils} sumR {summary.sum_rutils}")


class AlgoULBMiner:
    def __init__(self):
        self.start_timestamp = 0
        self.end_timestamp = 0
        self.hui_count = 0
        self.candidate_count = 0
        self.map_item_to_twu = {}
        self.map_item_to_support = {}
        self.writer = None
        self.map_fmap = collections.defaultdict(lambda: collections.defaultdict(int))
        self.enable_la_prune = True
        self.debug = False
        self.buffers_size = 200
        self.itemset_buffer = [0] * self.buffers_size
        self.utility_list_buffer = None

    def run_algorithm(self, input_file, output_file, min_utility):
        MemoryLogger.get_instance().reset()

        self.itemset_buffer = [0] * self.buffers_size
        self.map_fmap = collections.defaultdict(lambda: collections.defaultdict(int))

        self.start_timestamp = time.time()

        with open(output_file, 'w') as self.writer:
            self.process_input_file(input_file, min_utility)
            self.process_transactions(input_file, min_utility)

            MemoryLogger.get_instance().check_memory()
            self.utility_list_buffer.finish_building_single_items_utility_lists()

            self.fhm(self.itemset_buffer, 0, -1, 0, self.end_position, min_utility)

            MemoryLogger.get_instance().check_memory()

        self.end_timestamp = time.time()

    def process_input_file(self, input_file, min_utility):
        with open(input_file, 'r') as f:
            for line in f:
                if not line.strip() or line[0] in '#%@':
                    continue

                items, transaction_utility, _ = line.strip().split(':')
                items = list(map(int, items.split()))
                transaction_utility = int(transaction_utility)

                for item in items:
                    self.map_item_to_twu[item] = self.map_item_to_twu.get(item, 0) + transaction_utility
                    self.map_item_to_support[item] = self.map_item_to_support.get(item, 0) + 1

        sum_support = 0
        promising_items = [item for item in self.map_item_to_twu if self.map_item_to_twu[item] >= min_utility]
        for item in promising_items:
            sum_support += self.map_item_to_support[item]

        self.utility_list_buffer = UtilityListBuffer(sum_support, len(promising_items))

        promising_items.sort(key=lambda x: self.map_item_to_twu[x])

        self.map_item_to_utility_list = {}
        self.end_position = 0

        for item in promising_items:
            support = self.map_item_to_support[item]
            self.utility_list_buffer.create_a_new_utility_list(item, self.end_position)
            self.utility_list_buffer.allocate_space_for_elements(support)
            self.map_item_to_utility_list[item] = self.end_position
            self.end_position += 1

    def process_transactions(self, input_file, min_utility):
        with open(input_file, 'r') as f:
            tid = 0
            for line in f:
                if not line.strip() or line[0] in '#%@':
                    continue

                items, _, utility_values = line.strip().split(':')
                items = list(map(int, items.split()))
                utility_values = list(map(int, utility_values.split()))

                remaining_utility = 0
                new_twu = 0

                revised_transaction = []
                for item, utility in zip(items, utility_values):
                    if self.map_item_to_twu[item] >= min_utility:
                        revised_transaction.append((item, utility))
                        remaining_utility += utility
                        new_twu += utility

                revised_transaction.sort(key=lambda x: self.map_item_to_twu[x[0]])

                for i, (item, utility) in enumerate(revised_transaction):
                    remaining_utility -= utility
                    utility_list_position = self.map_item_to_utility_list[item]
                    self.utility_list_buffer.select_current_utility_list(utility_list_position)
                    self.utility_list_buffer.add_element_to_current_utility_list(tid, utility, remaining_utility)

                    map_fmap_item = self.map_fmap[item]
                    for j in range(i + 1, len(revised_transaction)):
                        item_after = revised_transaction[j][0]
                        map_fmap_item[item_after] += new_twu

                tid += 1

    def compare_items(self, item1, item2):
        compare = self.map_item_to_twu[item1] - self.map_item_to_twu[item2]
        return compare if compare != 0 else item1 - item2

    def fhm(self, prefix, prefix_length, pul_position, previous_start_position, previous_end_position, min_utility):
        for X in range(previous_start_position, previous_end_position):
            self.utility_list_buffer.select_current_utility_list(X)
            sum_iutils = self.utility_list_buffer.get_sum_iutil_current_utility_list()
            sum_rutils = self.utility_list_buffer.get_sum_rutil_current_utility_list()
            item_x = self.utility_list_buffer.get_item_current_utility_list()

            if sum_iutils >= min_utility:
                self.write_out(prefix, prefix_length, item_x, sum_iutils)

            if sum_iutils + sum_rutils >= min_utility:
                new_start_position = previous_end_position
                new_end_position = previous_end_position

                for Y in range(X + 1, previous_end_position):
                    self.utility_list_buffer.select_current_utility_list(Y)
                    item_y = self.utility_list_buffer.get_item_current_utility_list()

                    map_twu_f = self.map_fmap[item_x]
                    if map_twu_f and map_twu_f.get(item_y, 0) < min_utility:
                        continue

                    self.candidate_count += 1

                    if self.construct(pul_position, X, Y, min_utility, new_end_position, item_y, sum_iutils + sum_rutils):
                        new_end_position += 1

                prefix[prefix_length] = item_x
                self.fhm(prefix, prefix_length + 1, X, new_start_position, new_end_position, min_utility)

        MemoryLogger.get_instance().check_memory()

    def construct(self, p_position, px_position, py_position, min_utility, end_position, item_y, total_utility):
        self.utility_list_buffer.create_a_new_utility_list(item_y, end_position)

        self.utility_list_buffer.select_current_utility_list(px_position)
        count_x = self.utility_list_buffer.get_element_count_current_utility_list()

        self.utility_list_buffer.select_current_utility_list(py_position)
        count_y = self.utility_list_buffer.get_element_count_current_utility_list()

        count_p = 0
        if p_position >= 0:
            self.utility_list_buffer.select_current_utility_list(p_position)
            count_p = self.utility_list_buffer.get_element_count_current_utility_list()

        pos_x = pos_y = pos_p = 0

        while pos_x < count_x and pos_y < count_y:
            self.utility_list_buffer.select_current_utility_list(px_position)
            ex = self.utility_list_buffer.get_ith_element_in_current_utility_list(pos_x)

            self.utility_list_buffer.select_current_utility_list(py_position)
            ey = self.utility_list_buffer.get_ith_element_in_current_utility_list(pos_y)

            if ex.tid < ey.tid:
                if self.enable_la_prune:
                    total_utility -= (ex.iutils + ex.rutils)
                    if total_utility < min_utility:
                        return False
                pos_x += 1
            elif ex.tid > ey.tid:
                pos_y += 1
            else:
                ep_iutil = 0
                if p_position >= 0:
                    self.utility_list_buffer.select_current_utility_list(p_position)
                    ep = self.utility_list_buffer.get_ith_element_in_current_utility_list(pos_p)
                    while pos_p < count_p and ep.tid < ex.tid:
                        pos_p += 1
                        ep = self.utility_list_buffer.get_ith_element_in_current_utility_list(pos_p)
                    ep_iutil = ep.iutils if ep else 0

                self.utility_list_buffer.select_current_utility_list(end_position)
                self.utility_list_buffer.add_element_to_current_utility_list(ex.tid, ex.iutils + ey.iutils - ep_iutil, ey.rutils)
                pos_x += 1
                pos_y += 1

        return True

    def write_out(self, prefix, prefix_length, item, utility):
        self.hui_count += 1

        buffer = ' '.join(map(str, prefix[:prefix_length])) + f' {item} #UTIL: {utility}'
        self.writer.write(buffer + '\n')

    def print_stats(self):
        print("=============  ULB-Miner ALGORITHM - SPMF 0.2.19 - STATS =============")
        print(f" Total time ~ {self.end_timestamp - self.start_timestamp:.2f} ms")
        print(f" Memory ~ {MemoryLogger.get_instance().get_max_memory():.2f} MB")
        print(f" High-utility itemsets count : {self.hui_count}")
        print(f" Candidate count : {self.candidate_count}")

        if self.debug:
            pair_count = 0
            max_memory = self.get_object_size(self.map_fmap)
            for item, inner_map in self.map_fmap.items():
                max_memory += self.get_object_size(item)
                for inner_item, twu in inner_map.items():
                    pair_count += 1
                    max_memory += self.get_object_size(inner_item) + self.get_object_size(twu)

            print(f"CMAP size {max_memory:.2f} MB")
            print(f"PAIR COUNT {pair_count}")
        print("===================================================")

    @staticmethod
    def get_object_size(obj):
        import sys
        return sys.getsizeof(obj) / 1024 / 1024


class MainTestULBMiner:
    @staticmethod
    def main():
        input_file = MainTestULBMiner.file_to_path("DB_Utility.txt")
        output_file = "output.txt"
        min_utility = 30

        # Applying the algorithm
        algorithm = AlgoULBMiner()
        algorithm.run_algorithm(input_file, output_file, min_utility)
        algorithm.print_stats()

    @staticmethod
    def file_to_path(filename):
        path = os.path.join(os.path.dirname(__file__), filename)
        return urllib.parse.unquote(path)


if __name__ == "__main__":
    MainTestULBMiner.main()

