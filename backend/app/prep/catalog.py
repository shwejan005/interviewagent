"""Reviewed starter catalog for the preparation workspace.

The database owns the learner-facing problem contract. The frontend only renders
this data and the runner uses the stored harnesses to exercise solutions against
the stored test cases.
"""

TOPIC_SEED = (
    ("arrays", "Arrays", "Indexing, iteration, and invariant-driven array problems.", "FOUNDATION", []),
    ("hashing", "Hashing", "Maps and sets for lookup, counting, and deduplication.", "FOUNDATION", ["arrays"]),
    ("two-pointers", "Two Pointers", "Ordered scans that maintain a moving invariant.", "CORE", ["arrays"]),
    ("trees", "Trees", "Recursive and iterative traversal of hierarchical data.", "CORE", ["arrays"]),
    ("graphs", "Graphs", "Reachability, traversal, and shortest-path reasoning.", "CORE", ["trees"]),
)


def _python_harness(call: str) -> str:
    return (
        "import json\n"
        "_case = json.loads({{INPUT}})\n"
        f"_result = {call}\n"
        "print(json.dumps(_result, separators=(',', ':')))\n"
    )


def _javascript_harness(call: str) -> str:
    return (
        "const _case = JSON.parse({{INPUT}});\n"
        f"const _result = {call};\n"
        "console.log(JSON.stringify(_result));\n"
    )


PROBLEM_SEED = (
    {
        "slug": "two-sum",
        "topic_slug": "arrays",
        "title": "Two Sum",
        "prompt": "Given an integer array and a target, return the indices of two values that add to the target. Explain the time and space complexity.",
        "difficulty": "EASY",
        "estimated_minutes": 25,
        "expected_concepts": ["arrays", "hashing"],
        "constraints": ["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9", "Exactly one valid answer exists."],
        "hint": "A lookup map trades a little memory for a single linear scan.",
        "starter_code": {
            "python": "class Solution:\n    def two_sum(self, nums, target):\n        # Return the indices of the two values that add to target.\n        pass\n",
            "javascript": "class Solution {\n  twoSum(nums, target) {\n    const seen = new Map();\n    for (let index = 0; index < nums.length; index += 1) {\n      const complement = target - nums[index];\n      if (seen.has(complement)) return [seen.get(complement), index];\n      seen.set(nums[index], index);\n    }\n    return [];\n  }\n}\n",
        },
        "harnesses": {
            "python": _python_harness("Solution().two_sum(_case['nums'], _case['target'])"),
            "javascript": _javascript_harness("new Solution().twoSum(_case.nums, _case.target)"),
            "typescript": _javascript_harness("new Solution().twoSum(_case.nums, _case.target)"),
        },
        "test_cases": (
            {"title": "Basic pair", "input": {"nums": [2, 7, 11, 15], "target": 9}, "expected_output": "[0,1]", "explanation": "The first and second values add to nine."},
            {"title": "Pair in the middle", "input": {"nums": [3, 2, 4], "target": 6}, "expected_output": "[1,2]", "explanation": "The answer does not need to start at index zero."},
            {"title": "Duplicate values", "input": {"nums": [3, 3], "target": 6}, "expected_output": "[0,1]", "explanation": "The two equal values use different indices.", "is_hidden": True},
        ),
    },
    {
        "slug": "deduplicate-events",
        "topic_slug": "hashing",
        "title": "Deduplicate Events",
        "prompt": "Given an ordered stream of event IDs, return the first occurrence of each ID while preserving arrival order. State the memory trade-off.",
        "difficulty": "EASY",
        "estimated_minutes": 30,
        "expected_concepts": ["hashing", "arrays"],
        "constraints": ["Event IDs are non-empty strings.", "Preserve first-arrival order.", "Return a new collection."],
        "hint": "Use a set for membership and a list for the order you return.",
        "starter_code": {
            "python": "class Solution:\n    def deduplicate_events(self, events):\n        # Return first occurrences while preserving arrival order.\n        pass\n",
        },
        "harnesses": {"python": _python_harness("Solution().deduplicate_events(_case['events'])")},
        "test_cases": (
            {"title": "Repeated events", "input": {"events": ["a", "b", "a", "c"]}, "expected_output": "[\"a\",\"b\",\"c\"]", "explanation": "The second a is ignored."},
            {"title": "All repeated", "input": {"events": ["login", "login", "logout", "logout"]}, "expected_output": "[\"login\",\"logout\"]", "explanation": "Each event remains once."},
            {"title": "Empty stream", "input": {"events": []}, "expected_output": "[]", "explanation": "An empty stream returns an empty list.", "is_hidden": True},
        ),
    },
    {
        "slug": "longest-window",
        "topic_slug": "two-pointers",
        "title": "Longest Unique Window",
        "prompt": "Find the longest contiguous substring with no repeated characters. Explain the invariant maintained by your window.",
        "difficulty": "MEDIUM",
        "estimated_minutes": 35,
        "expected_concepts": ["two-pointers", "hashing"],
        "constraints": ["0 <= s.length <= 5 * 10^4", "s contains printable characters."],
        "hint": "Move the left edge only when the current window violates uniqueness.",
        "starter_code": {
            "python": "class Solution:\n    def longest_unique_window(self, s):\n        # Return the length of the longest substring without repeats.\n        pass\n",
        },
        "harnesses": {"python": _python_harness("Solution().longest_unique_window(_case['s'])")},
        "test_cases": (
            {"title": "Mixed repeats", "input": {"s": "abcabcbb"}, "expected_output": "3", "explanation": "abc is the longest unique window."},
            {"title": "Single repeated character", "input": {"s": "bbbbb"}, "expected_output": "1", "explanation": "The window can contain one b."},
            {"title": "Empty string", "input": {"s": ""}, "expected_output": "0", "explanation": "There is no non-empty window.", "is_hidden": True},
        ),
    },
    {
        "slug": "tree-level-order",
        "topic_slug": "trees",
        "title": "Tree Level Order",
        "prompt": "Return the values of a binary tree grouped by depth. The input uses level-order values with null for missing nodes.",
        "difficulty": "MEDIUM",
        "estimated_minutes": 35,
        "expected_concepts": ["trees", "queues"],
        "constraints": ["The tree has at most 2,000 nodes.", "Return values grouped by depth."],
        "hint": "A queue naturally processes one depth layer at a time.",
        "starter_code": {
            "python": "class Solution:\n    def tree_level_order(self, values):\n        # Values are level-order data; return non-null values by depth.\n        pass\n",
        },
        "harnesses": {"python": _python_harness("Solution().tree_level_order(_case['values'])")},
        "test_cases": (
            {"title": "Balanced levels", "input": {"values": [3, 9, 20, None, None, 15, 7]}, "expected_output": "[[3],[9,20],[15,7]]", "explanation": "Values are grouped by their depth."},
            {"title": "Empty tree", "input": {"values": []}, "expected_output": "[]", "explanation": "An empty tree has no levels."},
            {"title": "Only root", "input": {"values": [1]}, "expected_output": "[[1]]", "explanation": "The root is the first level.", "is_hidden": True},
        ),
    },
    {
        "slug": "shortest-route",
        "topic_slug": "graphs",
        "title": "Shortest Route",
        "prompt": "Given an unweighted graph as edge pairs, return the shortest number of edges between two nodes or -1 when no route exists.",
        "difficulty": "MEDIUM",
        "estimated_minutes": 45,
        "expected_concepts": ["graphs", "breadth-first-search"],
        "constraints": ["The graph is unweighted.", "Nodes are non-negative integers.", "The graph may be disconnected."],
        "hint": "Breadth-first search finds the first shortest path in an unweighted graph.",
        "starter_code": {
            "python": "class Solution:\n    def shortest_route(self, edges, start, end):\n        # Return the number of edges in the shortest route, or -1.\n        pass\n",
        },
        "harnesses": {"python": _python_harness("Solution().shortest_route(_case['edges'], _case['start'], _case['end'])")},
        "test_cases": (
            {"title": "Direct route", "input": {"edges": [[0, 1], [1, 2], [0, 2]], "start": 0, "end": 2}, "expected_output": "1", "explanation": "The direct edge is shortest."},
            {"title": "Disconnected nodes", "input": {"edges": [[0, 1]], "start": 0, "end": 3}, "expected_output": "-1", "explanation": "Node three cannot be reached."},
            {"title": "Same node", "input": {"edges": [[0, 1]], "start": 1, "end": 1}, "expected_output": "0", "explanation": "No edges are needed to reach the starting node.", "is_hidden": True},
        ),
    },
)
