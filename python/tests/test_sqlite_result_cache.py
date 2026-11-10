"""首页并发计算、清理与失败缓存边界；不访问金融数据。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
import unittest

from pmi.market_data.storage.result_cache import ResultCache


class ResultCacheTests(unittest.TestCase):
    def test_same_key_computes_once_and_hits_do_not_wait_for_other_calculation(self):
        cache = ResultCache()
        cache.get(('warm',), lambda: {'value': 'warm'})
        started, release = Event(), Event()
        state_lock = Lock()
        state = {'calls': 0, 'active': 0, 'maximum': 0}
        def calculate(block=False):
            with state_lock:
                state['calls'] += 1; state['active'] += 1
                state['maximum'] = max(state['maximum'], state['active'])
            try:
                if block:
                    started.set()
                    self.assertTrue(release.wait(3))
                return {'value': 'calculated'}
            finally:
                with state_lock: state['active'] -= 1
        with ThreadPoolExecutor(max_workers=5) as pool:
            first = pool.submit(cache.get, ('same',), lambda: calculate(True))
            try:
                self.assertTrue(started.wait(3))
                same = [pool.submit(cache.get, ('same',), calculate) for _ in range(2)]
                other = pool.submit(cache.get, ('different',), calculate)
                hit = pool.submit(cache.get, ('warm',), lambda: self.fail('warm key recalculated'))
                self.assertEqual(hit.result(timeout=2), {'value': 'warm'})
            finally:
                release.set()
            for future in [first, *same, other]:
                self.assertEqual(future.result(timeout=3), {'value': 'calculated'})
        self.assertEqual(state, {'calls': 2, 'active': 0, 'maximum': 1})

    def test_clear_during_calculation_does_not_repopulate_old_generation(self):
        cache, started, release = ResultCache(), Event(), Event()
        def old():
            started.set()
            self.assertTrue(release.wait(3))
            return {'value': 'old-request'}
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(cache.get, ('fixed',), old)
            try:
                self.assertTrue(started.wait(3)); cache.clear()
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3), {'value': 'old-request'})
        self.assertEqual(cache.get(('fixed',), lambda: {'value': 'new-calculation'}), {'value': 'new-calculation'})
        self.assertEqual(cache.get(('fixed',), lambda: self.fail('fresh result missing')), {'value': 'new-calculation'})

    def test_failure_capacity_and_mutation_do_not_pollute_other_results(self):
        cache = ResultCache()
        with self.assertRaises(ValueError):
            cache.get(('failed',), lambda: {'value': float('nan')})
        self.assertEqual(cache.get(('failed',), lambda: {'value': 'valid'}), {'value': 'valid'})
        for number in range(13): cache.get((number,), lambda number=number: {'nested': {'value': number}})
        self.assertEqual(cache.get((0,), lambda: {'value': 'recomputed'}), {'value': 'recomputed'})
        copy = cache.get((12,), lambda: self.fail('recent result evicted'))
        copy['nested']['value'] = 'mutated'
        self.assertEqual(cache.get((12,), lambda: self.fail('recent result evicted')), {'nested': {'value': 12}})
