"""原生结构节点与原Draft202012判定相等；未知语法必须回到原引擎。"""
import itertools
import unittest
from jsonschema import Draft202012Validator
from pmi.http_contract.schema_graph import validator


class SchemaGraphTests(unittest.TestCase):
    def test_supported_keywords_match_original_engine(self):
        definitions = {
            'number': {'type': 'number', 'minimum': 0},
            'integer': {'type': 'integer', 'enum': [0, 1, 2]},
            'string': {'type': 'string', 'minLength': 1, 'maxLength': 3, 'pattern': '^a'},
            'boolean': {'type': 'boolean', 'const': True},
            'nullable': {'anyOf': [{'$ref': '#/$defs/string'}, {'type': 'null'}]},
            'union': {'oneOf': [{'type': 'number'}, {'type': 'integer'}]},
            'array': {'type': 'array', 'minItems': 1, 'maxItems': 2, 'items': {'$ref': '#/$defs/nullable'}},
            'object': {'type': 'object', 'required': ['x'], 'properties': {'x': {'$ref': '#/$defs/integer'}}, 'additionalProperties': False},
            'map': {'type': 'object', 'additionalProperties': {'$ref': '#/$defs/string'}},
            'false': False, 'true': True,
            'format': {'type': 'string', 'format': 'date'},
            'optional': {'type': 'object', 'properties': {'x': {'type': 'string'}}, 'additionalProperties': True},
            'minimum': {'type': 'integer', 'minimum': 1},
            'strict_end': {'type': 'string', 'pattern': '^a$(?![\\s\\S])'},
            'exclusive': {'oneOf': [
                {'type': 'object', 'required': ['tag'], 'properties': {'tag': {'type': 'string', 'const': tag}}}
                for tag in ('a', 'b')]},
        }
        values = [None, True, False, -1, 0, 1, 1.0, 1.5, 2, 3, 10**100,
                  '', 'a', 'abc', 'abcd', 'b', 'a\n', '😀', '\ud800', '2026-02-30']
        values += [[x] for x in values] + [[], ['a', None], ['a', 'b', 'c']]
        values += [{'x': x} for x in values[:20]] + [{}, {'x': 1, 'extra': 0}, {'extra': 'abc'}]
        values += [{'tag': x} for x in ('a', 'b', 'c', None, True)]
        schemas = {'$defs': definitions}
        for name, value in itertools.product(definitions, values):
            with self.subTest(name=name, value=value):
                fast = validator(schemas, name)
                slow = Draft202012Validator({**schemas, '$ref': '#/$defs/' + name})
                self.assertEqual(fast.is_valid(value), slow.is_valid(value))

    def test_native_path_and_failure_fallback_keep_original_acceptance(self):
        schemas = {'$defs': {'root': {'type': 'integer', 'enum': [0, 1, 2]}}}
        fast = validator(schemas, 'root')
        self.assertNotIsInstance(fast, Draft202012Validator)
        # 原Schema承认1.0为整数，但严格原生节点拒绝；回退须保持原接受集。
        self.assertTrue(fast.is_valid(1.0))
        self.assertFalse(fast.is_valid(True))
        self.assertFalse(fast.is_valid('1'))

    def test_unsupported_assertions_fallback_not_silently_pass(self):
        for rule in [{'not': {'type': 'null'}}, {'type': 'array', 'uniqueItems': True},
                     {'type': 'number', 'maximum': 2}, {'$ref': '#/$defs/value', 'type': 'string'}]:
            schemas = {'$defs': {'root': rule, 'value': {'type': 'number'}}}
            result = validator(schemas, 'root')
            self.assertIsInstance(result, Draft202012Validator)
            for value in (None, 3, [1, 1], 'hello'):
                self.assertEqual(result.is_valid(value), Draft202012Validator({**schemas, '$ref': '#/$defs/root'}).is_valid(value))


if __name__ == '__main__':
    unittest.main()
