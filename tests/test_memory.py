import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from memorylib.demo import populate
from memorylib.evaluation import evaluate
from memorylib.indexing import build_indices
from memorylib.model import MemoryError, Store, json_text, parse_document, render_document, safe_path
from memorylib.operations import impact, init_domain, manage, managed_files, new_memory, transaction
from memorylib.retrieval import read_document, recall
from memorylib.validation import validate


class MemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.base_temp.name) / 'vault'
        shutil.copytree(ROOT, cls.base, ignore=shutil.ignore_patterns('.git', '.venv', '__pycache__', 'runs'))
        populate(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.base_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'vault'
        shutil.copytree(self.base, self.root)

    def edit(self, identity, meta=None, body=None):
        doc = Store(self.root).by_id[identity]
        doc.meta.update(meta or {})
        (self.root / doc.path).write_text(render_document(doc.meta, doc.body if body is None else body), encoding='utf-8')
        return doc

    def errors(self, strict=False):
        return [i for i in validate(self.root, strict)[1] if i.severity == 'error']

    def ids(self, result):
        return {x['id'] for key in ('hits', 'related', 'global') for x in result[key]}

    def test_complete_demo_valid(self):
        self.assertEqual(self.errors(True), [])

    def test_index_idempotent_and_preserves_prose(self):
        path = self.root / 'domains/parcels/INDEX.md'
        path.write_text('手写导航\n' + path.read_text(encoding='utf-8'), encoding='utf-8')
        build_indices(self.root)
        before = managed_files(self.root)
        self.assertEqual(build_indices(self.root), [])
        self.assertEqual(before, managed_files(self.root))
        self.assertTrue(path.read_text(encoding='utf-8').startswith('手写导航'))

    def test_index_staleness_and_malformed_marker(self):
        self.edit('demo-query-interface', {'title': '新标题'})
        self.assertIn('index-stale', {i.code for i in self.errors()})
        build_indices(self.root)
        self.assertEqual(self.errors(), [])
        path = self.root / 'INDEX.md'
        path.write_text('不完整索引', encoding='utf-8')
        with self.assertRaises(MemoryError):
            build_indices(self.root)
        self.assertEqual(path.read_text(encoding='utf-8'), '不完整索引')

    def test_duplicate_id_and_yaml_key(self):
        doc = Store(self.root).by_id['demo-candidate']
        (self.root / 'inbox/duplicate.md').write_text(doc.raw, encoding='utf-8')
        self.assertTrue(any('Duplicate id' in i.message for i in self.errors()))
        with self.assertRaises(MemoryError):
            parse_document('x.md', '---\nid: a\nid: b\n---\nbody')

    def test_handwritten_index_links_checked(self):
        path = self.root / 'INDEX.md'
        path.write_text('[错误入口](missing.md)\n' + path.read_text(encoding='utf-8'), encoding='utf-8')
        self.assertIn('index-link', {i.code for i in self.errors()})

    def test_stored_suite_schema_and_gold_checked(self):
        path = self.root / 'evals/cases/user.yaml'
        path.write_text('schema_version: 1\nsuite_kind: user\ncases: wrong-shape\n', encoding='utf-8')
        self.assertIn('eval-schema', {i.code for i in self.errors()})
        path.write_text('schema_version: 1\nsuite_kind: user\ncases:\n- id: first\n  status: confirmed\n  query: query\n  required_ids: [missing-id]\n', encoding='utf-8')
        self.assertIn('eval-schema', {i.code for i in self.errors()})

    def test_bad_field_types_diagnosed_without_crash(self):
        path = self.root / Store(self.root).by_id['demo-retry-rule'].path
        original = path.read_text(encoding='utf-8')
        for field in ('id', 'title', 'summary', 'type', 'status', 'domain', 'sources', 'related', 'created'):
            with self.subTest(field=field):
                doc = parse_document('x.md', original)
                doc.meta[field] = [{'unexpected':'shape'}]
                path.write_text(render_document(doc.meta, doc.body), encoding='utf-8')
                self.assertTrue(self.errors())
                path.write_text(original, encoding='utf-8')

    def test_broken_id_anchor_and_file_source(self):
        self.edit('demo-timeout-runbook', {'related':['missing'], 'sources':[{'kind':'file','ref':'missing.txt'}]}, '[坏锚点](memory:demo-retry-rule#不存在)')
        self.assertTrue({'reference','source','link'} <= {i.code for i in self.errors()})

    def test_code_examples_are_not_live_links(self):
        self.edit('demo-retry-rule', body='## 约束\n`[占位](memory:missing)`\n```md\n[示例](missing.md)\n```\n')
        build_indices(self.root)
        self.assertEqual(self.errors(), [])

    def test_domain_category_and_status_placement(self):
        self.edit('demo-query-interface', {'domain':'garden'})
        self.assertIn('placement', {i.code for i in self.errors()})
        self.edit('demo-query-interface', {'domain':'parcels', 'type':'concept', 'status':'archived'})
        self.assertTrue({'category','placement'} <= {i.code for i in self.errors()})

    def test_unknown_category_rejected(self):
        (self.root / 'domains/parcels/unregistered').mkdir()
        self.assertIn('category', {i.code for i in self.errors()})

    def test_global_total_budget(self):
        path = self.root / 'memory.config.json'
        config = json.loads(path.read_text())
        config['global_max_chars'] = 10
        path.write_text(json_text(config))
        self.assertIn('global-budget', {i.code for i in self.errors()})

    def test_review_due_warning_and_archive_exemption(self):
        self.edit('demo-retry-rule', {'review_after':'2000-01-01'})
        self.edit('demo-old-rule', {'review_after':'2000-01-01'})
        build_indices(self.root)
        due = [i for i in validate(self.root, today=dt.date(2026,11,12))[1] if i.code == 'review-due']
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].severity, 'warning')
        self.assertIn('review-due', {i.code for i in self.errors(True)})

    def test_portable_paths_and_traversal(self):
        for value in ('../outside', '/absolute', 'inbox/CON.md', 'inbox/a:b.md', 'inbox/bad. ', 'inbox/a\\b.md'):
            with self.subTest(value=value), self.assertRaises(MemoryError):
                safe_path(self.root, value)

    def test_symlink_rejected(self):
        try:
            (self.root / 'inbox/link.md').symlink_to(self.root / 'spec/structure.md')
        except OSError:
            self.skipTest('Symlink creation unavailable')
        with self.assertRaises(MemoryError):
            Store(self.root)

    def test_exact_symbol_and_related_rule(self):
        result = recall(self.root, 'QueryParcelStatus', domain='parcels', top_k=1)
        self.assertEqual(result['hits'][0]['id'], 'demo-query-interface')
        self.assertIn('demo-retry-rule', self.ids(result))
        self.assertTrue(result['hits'][0]['content'].startswith('---'))

    def test_alias_and_domain_filter(self):
        result = recall(self.root, '回执一直查不到', domain='parcels', top_k=1)
        self.assertEqual(result['hits'][0]['id'], 'demo-timeout-runbook')
        self.assertEqual(recall(self.root, 'QueryParcelStatus', domain='garden')['hits'], [])
        with self.assertRaises(MemoryError):
            recall(self.root, 'anything', domain='unknown')

    def test_default_exclusions_and_explicit_opt_ins(self):
        for query in ('CANDIDATE_ONLY','OLD_PARCEL_POLICY','spec-metadata'):
            self.assertEqual(recall(self.root, query)['hits'], [])
        self.assertTrue(recall(self.root, 'spec-metadata', include_spec=True)['hits'])
        self.assertEqual(len(recall(self.root, 'OLD_PARCEL_POLICY', include_archived=True)['hits']), 1)

    def test_global_always_loaded(self):
        result = recall(self.root, 'NOMATCH99887')
        self.assertEqual(result['hits'], [])
        self.assertEqual(result['global'][0]['id'], 'demo-global')

    def test_cross_domain_relation_requires_opt_in(self):
        self.edit('demo-query-interface', {'related':['demo-garden-rule']})
        build_indices(self.root)
        self.assertNotIn('demo-garden-rule', self.ids(recall(self.root, 'QueryParcelStatus', domain='parcels')))
        self.assertIn('demo-garden-rule', self.ids(recall(self.root, 'QueryParcelStatus', domain='parcels', cross_domain_related=True)))

    def test_context_budget_does_not_count_omitted_evidence(self):
        size = len(Store(self.root).by_id['demo-global'].raw)
        result = recall(self.root, 'QueryParcelStatus', max_chars=size)
        self.assertEqual(result['hits'], [])
        self.assertTrue(result['omitted'])
        self.assertEqual(result['used_chars'], size)
        with self.assertRaises(MemoryError):
            recall(self.root, 'QueryParcelStatus', max_chars=size-1)

    def test_explicit_read_status_guards(self):
        for identity in ('demo-candidate','demo-old-rule'):
            with self.assertRaises(MemoryError):
                read_document(self.root, identity)
        self.assertEqual(read_document(self.root, 'demo-candidate', include_inbox=True)['status'], 'candidate')
        self.assertEqual(read_document(self.root, 'demo-old-rule', include_archived=True)['status'], 'archived')

    def test_domain_init_minimal_and_nonoverwriting(self):
        init_domain(self.root, 'new-domain', '新领域', 'engineering')
        directory = self.root / 'domains/new-domain'
        self.assertTrue((directory / '0-overview/overview.md').exists())
        self.assertFalse((directory / '7-interfaces').exists())
        before = managed_files(self.root)
        with self.assertRaises(MemoryError):
            init_domain(self.root, 'new-domain', '覆盖标题')
        self.assertEqual(before, managed_files(self.root))

    def test_candidate_promotion_requires_content_and_sources(self):
        created = new_memory(self.root, '新概念', '解释用途', 'concept', 'parcels', '1-concepts')
        with self.assertRaises(MemoryError):
            manage(self.root, created['id'], 'promote', apply=True)
        self.edit(created['id'], {'sources':[{'kind':'note','ref':'测试约定'}]}, '## 概念\n这里是虚构示例。\n')
        build_indices(self.root)
        result = manage(self.root, created['id'], 'promote', apply=True)
        self.assertTrue(result['path'].startswith('domains/parcels/1-concepts/'))
        self.assertFalse((self.root / created['path']).exists())
        self.assertEqual(self.errors(), [])

    def test_move_preserves_id_links(self):
        result = manage(self.root, 'demo-retry-rule', 'move', 'domains/parcels/2-rules/renamed.md', True)
        self.assertTrue((self.root / result['path']).exists())
        self.assertEqual(self.errors(), [])
        self.assertIn('demo-timeout-runbook', {x['id'] for x in impact(self.root,'demo-retry-rule')['inbound']})

    def test_bad_move_rolls_back_everything(self):
        self.edit('demo-timeout-runbook', body='[依赖](../2-rules/retry.md)')
        build_indices(self.root)
        before = managed_files(self.root)
        with self.assertRaises(MemoryError):
            manage(self.root, 'demo-retry-rule', 'move', 'domains/parcels/2-rules/renamed.md', True)
        self.assertEqual(before, managed_files(self.root))
        self.assertFalse((self.root / '.memory.lock').exists())

    def test_delete_preview_and_referenced_delete(self):
        before = managed_files(self.root)
        self.assertFalse(manage(self.root,'demo-retry-rule','delete')['applied'])
        with self.assertRaises(MemoryError):
            manage(self.root,'demo-retry-rule','delete',apply=True)
        self.assertEqual(before, managed_files(self.root))

    def test_delete_cleans_index(self):
        manage(self.root, 'demo-candidate', 'delete', apply=True)
        self.assertNotIn('demo-candidate', (self.root/'inbox/INDEX.md').read_text(encoding='utf-8'))
        self.assertEqual(self.errors(), [])

    def test_archive_and_explicit_history(self):
        with self.assertRaises(MemoryError):
            manage(self.root,'demo-retry-rule','archive',apply=True)
        manage(self.root,'demo-garden-rule','archive',apply=True)
        self.assertNotIn('demo-garden-rule', self.ids(recall(self.root,'温室浇水')))
        self.assertIn('demo-garden-rule', self.ids(recall(self.root,'温室浇水',include_archived=True)))

    def test_supersedes_retains_history(self):
        self.edit('demo-query-interface', {'supersedes':['demo-garden-rule']})
        build_indices(self.root)
        manage(self.root,'demo-garden-rule','archive',apply=True)
        self.assertEqual(Store(self.root).by_id['demo-garden-rule'].meta['status'], 'archived')

    def test_lock_blocks_read_and_write(self):
        (self.root/'.memory.lock').write_text('active')
        with self.assertRaises(MemoryError):
            recall(self.root,'query')
        with self.assertRaises(MemoryError):
            init_domain(self.root,'new','新')

    def test_transaction_preserves_data_and_runs_attachments(self):
        for folder in ('data','runs'):
            directory = self.root/'domains/parcels/7-interfaces'/folder
            directory.mkdir()
            (directory/'example.json').write_text('{"example":true}')
        build_indices(self.root)
        before = managed_files(self.root)
        transaction(self.root, lambda stage: None)
        self.assertEqual(before, managed_files(self.root))

    def test_io_failure_restores_original_files(self):
        import memorylib.operations as ops
        before = managed_files(self.root)
        real_replace = ops.os.replace
        def fail_live(src,dst):
            # Windows temp directories can use an 8.3 alias (RUNNER~1).
            # The writer resolves its root, so compare canonical paths on both sides.
            if Path(dst).resolve().is_relative_to(self.root.resolve()):
                raise OSError('simulated disk error')
            return real_replace(src,dst)
        with patch.object(ops.os,'replace',side_effect=fail_live):
            with self.assertRaises(OSError):
                manage(self.root,'demo-candidate','delete',apply=True)
        self.assertEqual(before, managed_files(self.root))
        self.assertFalse((self.root/'.memory.lock').exists())

    def test_seven_synthetic_cases(self):
        report = evaluate(self.root,self.root/'examples/demo-suite.yaml')
        self.assertEqual(report['case_count'],7)
        self.assertEqual(report['pass_rate'],1)
        self.assertTrue(all(x['answer_status']=='not_evaluated' for x in report['cases']))

    def test_empty_suite_reports_not_evaluated(self):
        report = evaluate(self.root,self.root/'evals/cases/user.yaml')
        self.assertEqual(report['status'],'not_evaluated')
        self.assertIsNone(report['pass_rate'])

    def test_invalid_gold_id_is_setup_error(self):
        path = self.root/'evals/cases/bad.yaml'
        path.write_text('schema_version: 1\nsuite_kind: user\ncases:\n- id: bad\n  status: confirmed\n  query: question\n  required_ids: [missing]\n')
        with self.assertRaises(MemoryError):
            evaluate(self.root,path)

    def test_baseline_finds_individual_regression(self):
        suite = self.root/'examples/demo-suite.yaml'
        before = evaluate(self.root,suite)
        self.edit('demo-query-interface',{'symbols':[],'aliases':[],'title':'另一接口','summary':'无原标识符'},'## 说明\n占位内容。\n')
        build_indices(self.root)
        after = evaluate(self.root,suite,before)
        self.assertIn('exact-symbol',after['regressions'])

    def test_real_cli_status_codes(self):
        def run(script,*args):
            return subprocess.run([sys.executable,str(ROOT/'tools'/script),'--root',str(self.root),*args],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(run('check_memory.py','--strict').returncode,0)
        result=run('recall.py','query','--domain','missing')
        self.assertEqual(result.returncode,2)
        self.assertIn('Unknown domain',result.stderr)
        result=run('eval_recall.py','--suite','evals/cases/user.yaml')
        self.assertEqual(json.loads(result.stdout)['status'],'not_evaluated')


if __name__=='__main__':
    unittest.main()
