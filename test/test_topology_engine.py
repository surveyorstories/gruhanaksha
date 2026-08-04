import unittest
from qgis.core import QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsApplication
from gruhanaksha.topology_checker import TopologyEngine, TopologyError, TopologyFixer

# Initialize QgsApplication for tests
qgis_app = QgsApplication([], False)
qgis_app.initQgis()

class TestTopologyEngine(unittest.TestCase):

    def test_topology_engine_validity(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_layer", "memory")
        pr = layer.dataProvider()
        
        # Feature 1: Valid polygon
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(0,10), QgsPointXY(10,10), QgsPointXY(10,0), QgsPointXY(0,0)]]))
        
        # Feature 2: Self-intersecting bow-tie polygon
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(20,0), QgsPointXY(30,10), QgsPointXY(20,10), QgsPointXY(30,0), QgsPointXY(20,0)]]))
        
        pr.addFeatures([f1, f2])
        
        engine = TopologyEngine()
        options = {'check_validity': True, 'check_overlaps': False, 'check_duplicates': False}
        errors = engine.run_checks(layer, options)
        
        self.assertGreaterEqual(len(errors), 1)
        invalid_errs = [e for e in errors if e.error_type == 'Invalid Geometry']
        self.assertEqual(len(invalid_errs), 1)
        self.assertEqual(invalid_errs[0].feature_ids, [2])

    def test_topology_engine_overlaps(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_layer_overlap", "memory")
        pr = layer.dataProvider()
        
        # Feature 1: Outer polygon (0,0) to (10,10)
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(0,10), QgsPointXY(10,10), QgsPointXY(10,0), QgsPointXY(0,0)]]))
        
        # Feature 2: Inner polygon (2,2) to (8,8) - Completely contained inside f1 (100% overlap)
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(2,2), QgsPointXY(2,8), QgsPointXY(8,8), QgsPointXY(8,2), QgsPointXY(2,2)]]))
        
        pr.addFeatures([f1, f2])
        
        engine = TopologyEngine()
        options = {'check_validity': False, 'check_overlaps': True, 'overlap_tolerance': 0.0001}
        errors = engine.run_checks(layer, options)
        
        overlap_errs = [e for e in errors if e.error_type == 'Overlap']
        self.assertEqual(len(overlap_errs), 1)
        self.assertEqual(set(overlap_errs[0].feature_ids), {1, 2})

    def test_topology_engine_gaps(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_layer_gaps", "memory")
        pr = layer.dataProvider()
        
        # Two adjacent polygons separated by a tiny gap at X=10 to X=10.0001
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(0,10), QgsPointXY(10,10), QgsPointXY(10,0), QgsPointXY(0,0)]]))
        
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(10.0001,0), QgsPointXY(10.0001,10), QgsPointXY(20,10), QgsPointXY(20,0), QgsPointXY(10.0001,0)]]))
        
        pr.addFeatures([f1, f2])
        
        engine = TopologyEngine()
        options = {'check_gaps': True, 'gap_distance_tolerance': 0.0001}
        errors = engine.run_checks(layer, options)
        
        gap_errs = [e for e in errors if e.error_type == 'Gap / Sliver Void']
        self.assertEqual(len(gap_errs), 1)
        self.assertEqual(set(gap_errs[0].feature_ids), {1, 2})

    def test_topology_engine_prolonged_edges(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_layer_prolonged", "memory")
        pr = layer.dataProvider()
        
        # Feature 1: Polygon with a prolonged edge extending out of corner at (0, 15)
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0,0), QgsPointXY(0,10), QgsPointXY(0,15), QgsPointXY(0,10), QgsPointXY(10,10), QgsPointXY(10,0), QgsPointXY(0,0)
        ]]))
        
        # Feature 2 & 3: Clean adjacent polygons sharing a clean boundary edge at X=10
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(10,0), QgsPointXY(10,10), QgsPointXY(20,10), QgsPointXY(20,0), QgsPointXY(10,0)
        ]]))
        f3 = QgsFeature(3)
        f3.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(20,0), QgsPointXY(20,10), QgsPointXY(30,10), QgsPointXY(30,0), QgsPointXY(20,0)
        ]]))
        
        pr.addFeatures([f1, f2, f3])
        
        engine = TopologyEngine()
        options = {'check_prolonged_edges': True}
        errors = engine.run_checks(layer, options)
        
        prolonged_errs = [e for e in errors if 'Prolonged Edge' in e.error_type]
        # Only f1 has a prolonged spike, f2 and f3 are clean adjacent neighbors and should NOT be flagged as overshoots
        self.assertGreaterEqual(len(prolonged_errs), 1)
        for err in prolonged_errs:
            self.assertNotIn(2, err.feature_ids)
            self.assertNotIn(3, err.feature_ids)

    def test_topology_engine_duplicates(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_layer_duplicates", "memory")
        pr = layer.dataProvider()
        
        # Feature 1 & 2: Identical geometries
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(0,5), QgsPointXY(5,5), QgsPointXY(5,0), QgsPointXY(0,0)]]))
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(0,5), QgsPointXY(5,5), QgsPointXY(5,0), QgsPointXY(0,0)]]))
        
        pr.addFeatures([f1, f2])
        
        engine = TopologyEngine()
        options = {'check_validity': False, 'check_overlaps': False, 'check_duplicates': True}
        errors = engine.run_checks(layer, options)
        
        dup_errs = [e for e in errors if e.error_type == 'Duplicate Geometry']
        self.assertEqual(len(dup_errs), 1)
        self.assertEqual(set(dup_errs[0].feature_ids), {1, 2})

    def test_topology_engine_spikes(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_layer_spikes", "memory")
        pr = layer.dataProvider()
        
        # Polygon with a sharp spike vertex at (5, 50)
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0,0), QgsPointXY(0,10), QgsPointXY(5,50), QgsPointXY(5.1,10), QgsPointXY(10,10), QgsPointXY(10,0), QgsPointXY(0,0)
        ]]))
        
        pr.addFeatures([f1])
        
        engine = TopologyEngine()
        options = {'check_spikes': True, 'spike_angle_threshold': 15.0}
        errors = engine.run_checks(layer, options)
        
        spike_errs = [e for e in errors if e.error_type == 'Spike / Acute Vertex']
        self.assertEqual(len(spike_errs), 1)
        self.assertEqual(spike_errs[0].feature_ids, [1])
        self.assertAlmostEqual(spike_errs[0].location_x, 5.0, places=3)
        self.assertAlmostEqual(spike_errs[0].location_y, 50.0, places=3)

    def test_topology_engine_recheck_feature(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_layer_recheck", "memory")
        pr = layer.dataProvider()
        
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(0,10), QgsPointXY(10,10), QgsPointXY(10,0), QgsPointXY(0,0)]]))
        
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(5,5), QgsPointXY(5,15), QgsPointXY(15,15), QgsPointXY(15,5), QgsPointXY(5,5)]]))
        
        pr.addFeatures([f1, f2])
        
        engine = TopologyEngine()
        options = {'check_validity': True, 'check_overlaps': True, 'overlap_tolerance': 0.0001}
        
        # Initial run
        errors = engine.run_checks(layer, options)
        self.assertGreaterEqual(len(errors), 1)
        
        # Re-check only Feature 1
        recheck_errs = engine.run_checks_for_features(layer, [1], options)
        self.assertGreaterEqual(len(recheck_errs), 1)
        self.assertIn(1, recheck_errs[0].feature_ids)

    def test_topology_engine_multipart(self):
        layer = QgsVectorLayer("MultiPolygon?crs=EPSG:4326", "test_layer_multipart", "memory")
        pr = layer.dataProvider()
        
        poly1 = [QgsPointXY(0,0), QgsPointXY(0,2), QgsPointXY(2,2), QgsPointXY(0,0)]
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromMultiPolygonXY([[poly1]]))
        
        poly2 = [QgsPointXY(5,5), QgsPointXY(5,7), QgsPointXY(7,7), QgsPointXY(5,5)]
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromMultiPolygonXY([[poly1], [poly2]]))
        
        pr.addFeatures([f1, f2])
        
        engine = TopologyEngine()
        options = {'check_multipart': True}
        errors = engine.run_checks(layer, options)
        
        multipart_errs = [e for e in errors if e.error_type == 'Multipart Geometry']
        self.assertEqual(len(multipart_errs), 1)
        self.assertEqual(multipart_errs[0].feature_ids, [2])

    def test_selective_recheck_larger_id_bug(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_layer_recheck_bug", "memory")
        pr = layer.dataProvider()
        
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(0,10), QgsPointXY(10,10), QgsPointXY(10,0), QgsPointXY(0,0)]]))
        
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(5,5), QgsPointXY(5,15), QgsPointXY(15,15), QgsPointXY(15,5), QgsPointXY(5,5)]]))
        
        pr.addFeatures([f1, f2])
        
        engine = TopologyEngine()
        options = {'check_overlaps': True, 'overlap_tolerance': 0.0001}
        
        # Re-check only Feature 2 (the larger ID)
        recheck_errs = engine.run_checks_for_features(layer, [2], options)
        overlap_errs = [e for e in recheck_errs if e.error_type == 'Overlap']
        self.assertEqual(len(overlap_errs), 1)
        self.assertEqual(set(overlap_errs[0].feature_ids), {1, 2})

    def test_topology_fixer_invalid(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_fix_layer", "memory")
        pr = layer.dataProvider()
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(20,0), QgsPointXY(30,10), QgsPointXY(20,10), QgsPointXY(30,0), QgsPointXY(20,0)]]))
        pr.addFeatures([f1])
        
        layer.startEditing()
        success = TopologyFixer.fix_invalid_geometry(layer, 1)
        layer.commitChanges()
        self.assertTrue(success)
        self.assertTrue(layer.getFeature(1).geometry().isGeosValid())

    def test_canonical_duplicate_check(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_dup_canonical", "memory")
        pr = layer.dataProvider()
        
        # F1 and F2 are spatially identical, but starting point is shifted and F2 winding is reversed
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(0,5), QgsPointXY(5,5), QgsPointXY(5,0), QgsPointXY(0,0)]]))
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(5,5), QgsPointXY(0,5), QgsPointXY(0,0), QgsPointXY(5,0), QgsPointXY(5,5)]]))
        
        pr.addFeatures([f1, f2])
        engine = TopologyEngine()
        errors = engine.run_checks(layer, {'check_duplicates': True})
        dup_errs = [e for e in errors if e.error_type == 'Duplicate Geometry']
        self.assertEqual(len(dup_errs), 1)

    def test_enclosed_gap_check(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_enclosed_gaps", "memory")
        pr = layer.dataProvider()
        
        # Three touching triangles leaving an enclosed central triangular void
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(5,0), QgsPointXY(3,2), QgsPointXY(2,2), QgsPointXY(0,0)]]))
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(5,0), QgsPointXY(2.5,5), QgsPointXY(2.5,3), QgsPointXY(3,2), QgsPointXY(5,0)]]))
        f3 = QgsFeature(3)
        f3.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(2,2), QgsPointXY(2.5,3), QgsPointXY(2.5,5), QgsPointXY(0,0)]]))
        
        pr.addFeatures([f1, f2, f3])
        engine = TopologyEngine()
        errors = engine.run_checks(layer, {'check_enclosed_gaps': True})
        gap_errs = [e for e in errors if e.error_type == 'Enclosed Gap / Void']
        self.assertGreaterEqual(len(gap_errs), 1)

    def test_fix_overlap(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_fix_overlap", "memory")
        pr = layer.dataProvider()
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(0,10), QgsPointXY(10,10), QgsPointXY(10,0), QgsPointXY(0,0)]]))
        f2 = QgsFeature(2) # Area 25, overlaps f1 (area 100)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(8,0), QgsPointXY(8,10), QgsPointXY(13,10), QgsPointXY(13,0), QgsPointXY(8,0)]]))
        pr.addFeatures([f1, f2])
        
        layer.startEditing()
        success = TopologyFixer.fix_overlap_geometry(layer, 1, 2)
        layer.commitChanges()
        self.assertTrue(success)
        # Check that overlap is resolved
        self.assertAlmostEqual(layer.getFeature(2).geometry().intersection(layer.getFeature(1).geometry()).area(), 0.0, places=5)

    def test_fix_sliver(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_fix_sliver", "memory")
        pr = layer.dataProvider()
        # Large neighbor
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(0,10), QgsPointXY(10,10), QgsPointXY(10,0), QgsPointXY(0,0)]]))
        # Sliver sharing border at X=10
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(10,0), QgsPointXY(10,10), QgsPointXY(10.001,10), QgsPointXY(10.001,0), QgsPointXY(10,0)]]))
        pr.addFeatures([f1, f2])
        
        layer.startEditing()
        success = TopologyFixer.fix_sliver_geometry(layer, 2)
        layer.commitChanges()
        self.assertTrue(success)
        # Sliver should be deleted and merged into neighbor
        self.assertFalse(layer.getFeature(2).isValid())
        self.assertGreater(layer.getFeature(1).geometry().area(), 100.0)

    def test_fix_overshoot(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_fix_overshoot", "memory")
        pr = layer.dataProvider()
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromWkt('POLYGON((0 0, 0 10, 5 10, 5 15, 5 10, 10 10, 10 0, 0 0))'))
        pr.addFeatures([f1])
        
        layer.startEditing()
        success = TopologyFixer.fix_overshoot_geometry(layer, 1)
        layer.commitChanges()
        self.assertTrue(success)
        # Geometry should be valid and have no dangling line
        geom = layer.getFeature(1).geometry()
        self.assertTrue(geom.isGeosValid())
        self.assertNotIn("LineString", geom.asWkt())

    def test_localized_enclosed_gap_check(self):
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_local_gaps", "memory")
        pr = layer.dataProvider()
        
        # Three touching triangles leaving an enclosed central triangular void
        f1 = QgsFeature(1)
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(5,0), QgsPointXY(3,2), QgsPointXY(2,2), QgsPointXY(0,0)]]))
        f2 = QgsFeature(2)
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(5,0), QgsPointXY(2.5,5), QgsPointXY(2.5,3), QgsPointXY(3,2), QgsPointXY(5,0)]]))
        f3 = QgsFeature(3)
        f3.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(2,2), QgsPointXY(2.5,3), QgsPointXY(2.5,5), QgsPointXY(0,0)]]))
        # A far-away clean feature
        f4 = QgsFeature(4)
        f4.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(100,100), QgsPointXY(100,110), QgsPointXY(110,110), QgsPointXY(110,100), QgsPointXY(100,100)]]))
        
        pr.addFeatures([f1, f2, f3, f4])
        engine = TopologyEngine()
        # Selective check on f1, f2, f3. It should find the gap locally
        errors1 = engine.run_checks(layer, {'check_enclosed_gaps': True}, target_fids=[1, 2, 3])
        gap_errs1 = [e for e in errors1 if e.error_type == 'Enclosed Gap / Void']
        self.assertEqual(len(gap_errs1), 1)

        # Selective check on f4. It should NOT find the gap since f4 is far away and has no gaps
        errors2 = engine.run_checks(layer, {'check_enclosed_gaps': True}, target_fids=[4])
        gap_errs2 = [e for e in errors2 if e.error_type == 'Enclosed Gap / Void']
        self.assertEqual(len(gap_errs2), 0)

if __name__ == '__main__':
    unittest.main()
