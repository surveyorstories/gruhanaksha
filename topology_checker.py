# -*- coding: utf-8 -*-
"""
Topology Checker Module for Gruhanaksha Plugin
Provides comprehensive quality control for Polygon and MultiPolygon vector layers.
"""

import os
import csv
import math
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsSpatialIndex,
    QgsRectangle, QgsPointXY, QgsField, QgsProject, QgsMapLayerProxyModel,
    QgsTask, QgsApplication, QgsWkbTypes
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QCheckBox, QDoubleSpinBox, QPushButton, QProgressBar, QComboBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QLabel, QFileDialog,
    QTabWidget, QWidget, QAbstractItemView, QListWidget, QListWidgetItem
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.gui import QgsMapLayerComboBox, QgsRubberBand, QgsVertexMarker

# PyQt5 / PyQt6 compatibility for Qt enums
CHECKED = Qt.CheckState.Checked
USER_ROLE = Qt.ItemDataRole.UserRole
ITEM_IS_USER_CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable


class TopologyError:
    """Represents an identified topological anomaly or error."""
    def __init__(self, error_type, feature_ids, description, location_x=0.0, location_y=0.0, geometry=None, feature_layers=None):
        self.error_type = error_type
        self.feature_ids = feature_ids
        self.description = description
        self.location_x = location_x
        self.location_y = location_y
        self.geometry = geometry
        self.feature_layers = feature_layers if feature_layers is not None else []


class TopologyEngine:
    """Core evaluation engine running geometry checks without external dependencies."""

    def canonicalize_ring(self, ring):
        if not ring:
            return ()
        pts = ring[:-1] if ring[0] == ring[-1] else ring
        if not pts:
            return ()
        coords = [(round(p.x(), 8), round(p.y(), 8)) for p in pts]
        n = len(coords)
        rotations = []
        for i in range(n):
            rotations.append(tuple(coords[i:] + coords[:i]))
        coords_rev = coords[::-1]
        for i in range(n):
            rotations.append(tuple(coords_rev[i:] + coords_rev[:i]))
        return min(rotations)

    def canonicalize_polygon(self, geom):
        if geom.isEmpty():
            return ()
        poly_list = geom.asMultiPolygon() if geom.isMultipart() else [geom.asPolygon()]
        canonical_parts = []
        for poly in poly_list:
            ext_ring = self.canonicalize_ring(poly[0])
            int_rings = tuple(sorted(self.canonicalize_ring(r) for r in poly[1:]))
            canonical_parts.append((ext_ring, int_rings))
        return tuple(sorted(canonical_parts))

    def _get_polygon_parts(self, geom):
        if not geom or geom.isEmpty():
            return []
        comps = geom.coerceToType(QgsWkbTypes.Type.Polygon)
        return [c for c in comps if c.type() == QgsWkbTypes.GeometryType.PolygonGeometry and not c.isEmpty()]

    def run_checks(self, layer_or_features, options: dict, progress_callback=None, target_fids=None):
        errors = []
        if not layer_or_features:
            return errors

        if isinstance(layer_or_features, list):
            features = layer_or_features
        else:
            if not layer_or_features.isValid():
                return errors
            features = list(layer_or_features.getFeatures())

        total_count = len(features)
        if total_count == 0:
            return errors

        # Cache features in memory and build spatial index once
        features_dict = {}
        spatial_index = QgsSpatialIndex()
        for f in features:
            features_dict[f.id()] = f
            if f.geometry() and not f.geometry().isEmpty():
                spatial_index.addFeature(f)

        target_set = set(target_fids) if target_fids is not None else None

        # 1. Check Invalid Geometry / Self-Intersections
        if options.get('check_validity', True):
            for idx, feat in enumerate(features):
                if target_set is not None and feat.id() not in target_set:
                    continue
                if progress_callback:
                    progress_callback(int((idx / total_count) * 15))
                geom = feat.geometry()
                if not geom or geom.isEmpty():
                    errors.append(TopologyError('Empty Geometry', [feat.id()], 'Feature has empty or null geometry'))
                    continue

                if not geom.isGeosValid():
                    err_msg = geom.validateGeometry()
                    desc = f"Invalid Geometry: {err_msg[0].what()}" if err_msg else "Invalid Geometry / Self-intersection"
                    centroid = geom.centroid().asPoint() if not geom.centroid().isEmpty() else QgsPointXY(0, 0)
                    errors.append(TopologyError('Invalid Geometry', [feat.id()], desc, centroid.x(), centroid.y(), geom))

        # 2. Check Spike Vertices & Acute Angles
        if options.get('check_spikes', True):
            angle_thresh = options.get('spike_angle_threshold', 15.0)
            for idx, feat in enumerate(features):
                if target_set is not None and feat.id() not in target_set:
                    continue
                if progress_callback:
                    progress_callback(15 + int((idx / total_count) * 20))
                geom = feat.geometry()
                if not geom or geom.isEmpty():
                    continue

                # Extract polygon rings
                polygon_list = geom.asMultiPolygon() if geom.isMultipart() else [geom.asPolygon()]

                for poly in polygon_list:
                    for ring in poly:
                        if len(ring) < 4:
                            continue
                        # Ring vertices excluding redundant end point if identical to start
                        pts = ring[:-1] if ring[0] == ring[-1] else ring
                        num_pts = len(pts)
                        for i in range(num_pts):
                            p_prev = pts[i - 1]
                            p_curr = pts[i]
                            p_next = pts[(i + 1) % num_pts]

                            v1x, v1y = p_curr.x() - p_prev.x(), p_curr.y() - p_prev.y()
                            v2x, v2y = p_next.x() - p_curr.x(), p_next.y() - p_curr.y()

                            len1 = math.hypot(v1x, v1y)
                            len2 = math.hypot(v2x, v2y)

                            if len1 == 0 or len2 == 0:
                                errors.append(TopologyError(
                                    'Spike / Acute Vertex', [feat.id()],
                                    f"Duplicate consecutive vertex at ({p_curr.x():.4f}, {p_curr.y():.4f})",
                                    p_curr.x(), p_curr.y(), QgsGeometry.fromPointXY(p_curr)
                                ))
                                continue

                            # Cosine of turn angle
                            cos_turn = (v1x * v2x + v1y * v2y) / (len1 * len2)
                            cos_turn = max(-1.0, min(1.0, cos_turn))

                            # Interior angle in degrees at p_curr
                            cos_interior = -cos_turn
                            cos_interior = max(-1.0, min(1.0, cos_interior))
                            interior_angle_deg = math.degrees(math.acos(cos_interior))

                            if interior_angle_deg < angle_thresh:
                                desc = f"Spike vertex at ({p_curr.x():.4f}, {p_curr.y():.4f}) with acute interior angle {interior_angle_deg:.1f}°"
                                errors.append(TopologyError(
                                    'Spike / Acute Vertex', [feat.id()], desc,
                                    p_curr.x(), p_curr.y(), QgsGeometry.fromPointXY(p_curr)
                                ))

        # 3. Check Prolonged Edges / Boundary Overshoots / Dangling Segments
        if options.get('check_prolonged_edges', True):
            # Pre-compute boundary lines for all features to avoid recalculation in candidate loops
            boundary_dict = {}
            for f in features:
                # If target_set is active, we only need boundary lines for target features and their potential neighbors
                # But to be safe and simple, we compute for all (fast in-memory)
                geom = f.geometry()
                if geom and not geom.isEmpty():
                    lines = []
                    poly_list = geom.asMultiPolygon() if geom.isMultipart() else [geom.asPolygon()]
                    for p in poly_list:
                        for ring in p:
                            lines.append(ring)
                    boundary_dict[f.id()] = QgsGeometry.fromMultiPolylineXY(lines) if lines else None

            seen_overshoot_pairs = set()
            for idx, feat in enumerate(features):
                if target_set is not None and feat.id() not in target_set:
                    continue
                geom = feat.geometry()
                if not geom or geom.isEmpty():
                    continue

                polygon_list = geom.asMultiPolygon() if geom.isMultipart() else [geom.asPolygon()]
                for poly in polygon_list:
                    for ring in poly:
                        if len(ring) < 4:
                            continue
                        pts = ring[:-1] if ring[0] == ring[-1] else ring
                        num_pts = len(pts)
                        for i in range(num_pts):
                            p_prev = pts[i - 1]
                            p_curr = pts[i]
                            p_next = pts[(i + 1) % num_pts]

                            v1x, v1y = p_curr.x() - p_prev.x(), p_curr.y() - p_prev.y()
                            v2x, v2y = p_next.x() - p_curr.x(), p_next.y() - p_curr.y()
                            len1 = math.hypot(v1x, v1y)
                            len2 = math.hypot(v2x, v2y)

                            if len1 > 0 and len2 > 0:
                                cos_turn = (v1x * v2x + v1y * v2y) / (len1 * len2)
                                if cos_turn < -0.99999 or math.hypot(p_prev.x() - p_next.x(), p_prev.y() - p_next.y()) < 0.000001:
                                    desc = f"Prolonged edge / Dangling segment extending out at ({p_curr.x():.4f}, {p_curr.y():.4f})"
                                    errors.append(TopologyError(
                                        'Prolonged Edge / Overshoot', [feat.id()], desc,
                                        p_curr.x(), p_curr.y(), QgsGeometry.fromPointXY(p_curr)
                                    ))

                # Check if boundary edges prolong into neighbor feature interior (true overshoot)
                candidates = spatial_index.intersects(geom.boundingBox())
                boundary_a = boundary_dict.get(feat.id())

                for cand_id in candidates:
                    if cand_id == feat.id():
                        continue
                    if target_set is not None and feat.id() not in target_set and cand_id not in target_set:
                        continue
                    pair = (min(feat.id(), cand_id), max(feat.id(), cand_id))
                    if pair in seen_overshoot_pairs:
                        continue
                    seen_overshoot_pairs.add(pair)
                    featB = features_dict.get(cand_id)
                    if not featB:
                        continue
                    geomB = featB.geometry()
                    if not geomB or geomB.isEmpty():
                        continue

                    if boundary_a and boundary_a.intersects(geomB):
                        line_inter = boundary_a.intersection(geomB)
                        if not line_inter.isEmpty() and line_inter.length() > 0.0001 and line_inter.area() == 0.0:
                            boundary_b = boundary_dict.get(cand_id)
                            
                            # True overshoot must not lie exactly on the neighbor's boundary line
                            true_overshoot = line_inter.difference(boundary_b) if boundary_b else line_inter
                            if not true_overshoot.isEmpty() and true_overshoot.length() > 0.0001:
                                centroid = true_overshoot.centroid().asPoint() if not true_overshoot.centroid().isEmpty() else QgsPointXY(0,0)
                                desc = f"Prolonged edge entering neighbor FID {cand_id} (Length: {true_overshoot.length():.4f} units)"
                                errors.append(TopologyError(
                                    'Prolonged Edge / Overshoot', [feat.id(), cand_id], desc,
                                    centroid.x(), centroid.y(), true_overshoot
                                ))

        # 4. Check Overlaps (Supports partial, boundary, and 100% containment overlaps)
        if options.get('check_overlaps', True):
            overlap_tol = options.get('overlap_tolerance', 0.0001)
            seen_pairs = set()
            for idx, feat in enumerate(features):
                if target_set is not None and feat.id() not in target_set:
                    continue
                if progress_callback:
                    progress_callback(35 + int((idx / total_count) * 20))
                geomA = feat.geometry()
                if not geomA or geomA.isEmpty():
                    continue

                candidates = spatial_index.intersects(geomA.boundingBox())
                for candidate_id in candidates:
                    if candidate_id == feat.id():
                        continue
                    if target_set is not None and feat.id() not in target_set and candidate_id not in target_set:
                        continue
                    pair = (min(feat.id(), candidate_id), max(feat.id(), candidate_id))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    featB = features_dict.get(candidate_id)
                    if not featB:
                        continue
                    geomB = featB.geometry()
                    if not geomB or geomB.isEmpty():
                        continue

                    if geomA.boundingBox().intersects(geomB.boundingBox()):
                        if geomA.intersects(geomB):
                            inter = geomA.intersection(geomB)
                            if not inter.isEmpty() and inter.area() > overlap_tol:
                                centroid = inter.centroid().asPoint() if not inter.centroid().isEmpty() else geomA.centroid().asPoint()
                                desc = f"Overlaps with FID {candidate_id} (Area: {inter.area():.4f} sq units)"
                                errors.append(TopologyError('Overlap', [feat.id(), candidate_id], desc, centroid.x(), centroid.y(), inter))

        # 5. Check Gaps / Voids between Polygons (Must be strictly continuous / zero gap tolerance)
        if options.get('check_gaps', True):
            gap_tol = options.get('gap_distance_tolerance', 0.000001)
            seen_gap_pairs = set()
            for idx, feat in enumerate(features):
                if target_set is not None and feat.id() not in target_set:
                    continue
                if progress_callback:
                    progress_callback(55 + int((idx / total_count) * 25))
                geomA = feat.geometry()
                if not geomA or geomA.isEmpty():
                    continue

                bbox_expanded = geomA.boundingBox()
                bbox_expanded.grow(max(gap_tol * 2.0, 1.0))
                candidates = spatial_index.intersects(bbox_expanded)

                for candidate_id in candidates:
                    if candidate_id == feat.id():
                        continue
                    if target_set is not None and feat.id() not in target_set and candidate_id not in target_set:
                        continue
                    pair = (min(feat.id(), candidate_id), max(feat.id(), candidate_id))
                    if pair in seen_gap_pairs:
                        continue
                    seen_gap_pairs.add(pair)

                    featB = features_dict.get(candidate_id)
                    if not featB:
                        continue
                    geomB = featB.geometry()
                    if not geomB or geomB.isEmpty():
                        continue

                    # Fast Bounding Box pruning
                    rectA = geomA.boundingBox()
                    rectB = geomB.boundingBox()
                    dx = max(0.0, rectA.xMinimum() - rectB.xMaximum(), rectB.xMinimum() - rectA.xMaximum())
                    dy = max(0.0, rectA.yMinimum() - rectB.yMaximum(), rectB.yMinimum() - rectA.yMaximum())
                    dist_bbox = math.hypot(dx, dy)
                    if dist_bbox > gap_tol:
                        continue

                    # Strict Gap Rule: If adjacent features do NOT touch or intersect, ANY distance > 0.0 up to gap_tol is an unmapped gap error!
                    if not geomA.intersects(geomB) and not geomA.touches(geomB):
                        dist = geomA.distance(geomB)
                        if 0.0 < dist <= gap_tol:
                            gap_geom = geomA.shortestLine(geomB)
                            if not gap_geom.isEmpty():
                                cent = gap_geom.centroid().asPoint() if not gap_geom.centroid().isEmpty() else QgsPointXY(0,0)
                                mid_x = cent.x()
                                mid_y = cent.y()
                            else:
                                ptA = geomA.centroid().asPoint()
                                ptB = geomB.centroid().asPoint()
                                mid_x = (ptA.x() + ptB.x()) / 2.0
                                mid_y = (ptA.y() + ptB.y()) / 2.0
                            desc = f"Unmapped Gap / Void between FID {feat.id()} and FID {candidate_id} (Distance: {dist:.6f} units)"
                            errors.append(TopologyError('Gap / Sliver Void', [feat.id(), candidate_id], desc, mid_x, mid_y, gap_geom))

        # 6. Check Duplicate Geometries
        if options.get('check_duplicates', True):
            seen_geoms = {}
            for feat in features:
                geom = feat.geometry()
                if not geom or geom.isEmpty():
                    continue
                canonical_key = self.canonicalize_polygon(geom)
                if canonical_key in seen_geoms:
                    other_id = seen_geoms[canonical_key]
                    # If target_set is active, we only flag if either features are in target_set
                    if target_set is not None and feat.id() not in target_set and other_id not in target_set:
                        continue
                    centroid = geom.centroid().asPoint()
                    errors.append(TopologyError('Duplicate Geometry', [feat.id(), other_id], f"Identical geometry to FID {other_id}", centroid.x(), centroid.y(), geom))
                else:
                    seen_geoms[canonical_key] = feat.id()

        # 7. Check Multipart Geometries
        if options.get('check_multipart', True):
            for feat in features:
                if target_set is not None and feat.id() not in target_set:
                    continue
                geom = feat.geometry()
                if geom and geom.isMultipart() and geom.constGet().partCount() > 1:
                    centroid = geom.centroid().asPoint()
                    num_parts = geom.constGet().partCount()
                    errors.append(TopologyError('Multipart Geometry', [feat.id()], f"Feature has {num_parts} disjoint polygon parts", centroid.x(), centroid.y(), geom))

        # 8. Check Minimum Area / Slivers
        if options.get('check_min_area', True):
            min_area = options.get('min_area_tolerance', 0.01)
            for feat in features:
                if target_set is not None and feat.id() not in target_set:
                    continue
                geom = feat.geometry()
                if geom and not geom.isEmpty() and geom.area() < min_area:
                    centroid = geom.centroid().asPoint()
                    errors.append(TopologyError('Micro Polygon / Sliver', [feat.id()], f"Area ({geom.area():.6f}) is below minimum threshold ({min_area})", centroid.x(), centroid.y(), geom))

        # 9. Check Enclosed Gaps / Voids
        if options.get('check_enclosed_gaps', True):
            if target_set is not None:
                # Localized gap check around target features
                target_geoms = [features_dict[fid].geometry() for fid in target_set if fid in features_dict]
                if target_geoms:
                    # Combine target bounding boxes
                    # Combine target bounding boxes
                    bbox = QgsRectangle(target_geoms[0].boundingBox())
                    for g in target_geoms[1:]:
                        bbox.combineExtentWith(g.boundingBox())
                    # Grow bbox slightly to include neighbor features
                    bbox.grow(50.0)
                    
                    # Find candidate features intersecting the expanded bounding box
                    candidate_ids = spatial_index.intersects(bbox)
                    local_geoms = []
                    for cid in candidate_ids:
                        f = features_dict.get(cid)
                        if f and f.geometry() and not f.geometry().isEmpty():
                            local_geoms.extend(self._get_polygon_parts(f.geometry().makeValid()))
                    
                    if local_geoms:
                        union_geom = QgsGeometry.unaryUnion(local_geoms)
                        if union_geom and not union_geom.isEmpty():
                            polys = union_geom.asMultiPolygon() if union_geom.isMultipart() else [union_geom.asPolygon()]
                            for poly in polys:
                                for int_ring in poly[1:]:
                                    hole_geom = QgsGeometry.fromPolygonXY([int_ring])
                                    # Only report if the hole intersects the original target bounding box
                                    target_bbox = QgsRectangle(target_geoms[0].boundingBox())
                                    for g in target_geoms[1:]:
                                        target_bbox.combineExtentWith(g.boundingBox())
                                    if hole_geom.boundingBox().intersects(target_bbox):
                                        centroid = hole_geom.centroid().asPoint()
                                        desc = f"Enclosed Gap / Void (Area: {hole_geom.area():.4f} sq units)"
                                        
                                        # Find surrounding feature IDs
                                        surrounding_fids = []
                                        expanded_hole = hole_geom.boundingBox()
                                        expanded_hole.grow(0.1)
                                        candidates = spatial_index.intersects(expanded_hole)
                                        for cid in candidates:
                                            f = features_dict.get(cid)
                                            if f and f.geometry() and f.geometry().intersects(hole_geom):
                                                surrounding_fids.append(cid)

                                        errors.append(TopologyError(
                                            'Enclosed Gap / Void',
                                            surrounding_fids,
                                            desc,
                                            centroid.x(),
                                            centroid.y(),
                                            hole_geom
                                        ))
            else:
                # Full layer check
                valid_geoms = []
                for f in features:
                    if f.geometry() and not f.geometry().isEmpty():
                        valid_geoms.extend(self._get_polygon_parts(f.geometry().makeValid()))
                if valid_geoms:
                    union_geom = QgsGeometry.unaryUnion(valid_geoms)
                    if union_geom and not union_geom.isEmpty():
                        polys = union_geom.asMultiPolygon() if union_geom.isMultipart() else [union_geom.asPolygon()]
                        for poly in polys:
                            for int_ring in poly[1:]:
                                hole_geom = QgsGeometry.fromPolygonXY([int_ring])
                                centroid = hole_geom.centroid().asPoint()
                                desc = f"Enclosed Gap / Void (Area: {hole_geom.area():.4f} sq units)"
                                
                                # Find surrounding feature IDs
                                surrounding_fids = []
                                expanded_hole = hole_geom.boundingBox()
                                expanded_hole.grow(0.1)
                                candidates = spatial_index.intersects(expanded_hole)
                                for cid in candidates:
                                    f = features_dict.get(cid)
                                    if f and f.geometry() and f.geometry().intersects(hole_geom):
                                        surrounding_fids.append(cid)

                                errors.append(TopologyError(
                                    'Enclosed Gap / Void',
                                    surrounding_fids,
                                    desc,
                                    centroid.x(),
                                    centroid.y(),
                                    hole_geom
                                ))

        # 10. Check Missing Nodes / Line Intersections (T-Junctions & Boundary Crossings)
        if options.get('check_missing_nodes', True):
            node_tol = options.get('missing_node_tolerance', 0.1)
            boundary_dict = {}
            vertices_dict = {}
            for f in features:
                geom = f.geometry()
                if geom and not geom.isEmpty():
                    lines = []
                    pts = []
                    poly_list = geom.asMultiPolygon() if geom.isMultipart() else [geom.asPolygon()]
                    for p in poly_list:
                        for ring in p:
                            lines.append(ring)
                            pts.extend(ring[:-1] if (len(ring) > 1 and ring[0] == ring[-1]) else ring)
                    boundary_dict[f.id()] = QgsGeometry.fromMultiPolylineXY(lines) if lines else None
                    vertices_dict[f.id()] = pts

            seen_missing_pairs = set()
            seen_node_errors = set()
            for idx, featA in enumerate(features):
                if target_set is not None and featA.id() not in target_set:
                    continue
                geomA = featA.geometry()
                if not geomA or geomA.isEmpty():
                    continue

                bbox_expanded = geomA.boundingBox()
                bbox_expanded.grow(max(node_tol * 2.0, 0.5))
                candidates = spatial_index.intersects(bbox_expanded)

                bA = boundary_dict.get(featA.id())
                vA = vertices_dict.get(featA.id(), [])
                if not bA:
                    continue

                for cand_id in candidates:
                    if cand_id == featA.id():
                        continue
                    if target_set is not None and featA.id() not in target_set and cand_id not in target_set:
                        continue
                    pair = (min(featA.id(), cand_id), max(featA.id(), cand_id))
                    if pair in seen_missing_pairs:
                        continue
                    seen_missing_pairs.add(pair)

                    featB = features_dict.get(cand_id)
                    if not featB:
                        continue
                    geomB = featB.geometry()
                    if not geomB or geomB.isEmpty():
                        continue

                    bB = boundary_dict.get(cand_id)
                    vB = vertices_dict.get(cand_id, [])
                    if not bB:
                        continue

                    # 1. Vertices of A touching/on boundary of B (Missing node in B)
                    for pt in vA:
                        if bB.distance(QgsGeometry.fromPointXY(pt)) <= node_tol:
                            if not any(pt.distance(pB) <= node_tol for pB in vB):
                                err_key = (cand_id, round(pt.x(), 4), round(pt.y(), 4))
                                if err_key not in seen_node_errors:
                                    seen_node_errors.add(err_key)
                                    desc = f"Missing node / T-junction at ({pt.x():.4f}, {pt.y():.4f}) in FID {cand_id} (shared with FID {featA.id()})"
                                    errors.append(TopologyError(
                                        'Missing Node / Line Intersection', [cand_id, featA.id()], desc,
                                        pt.x(), pt.y(), QgsGeometry.fromPointXY(pt)
                                    ))

                    # 2. Vertices of B touching/on boundary of A (Missing node in A)
                    for pt in vB:
                        if bA.distance(QgsGeometry.fromPointXY(pt)) <= node_tol:
                            if not any(pt.distance(pA) <= node_tol for pA in vA):
                                err_key = (featA.id(), round(pt.x(), 4), round(pt.y(), 4))
                                if err_key not in seen_node_errors:
                                    seen_node_errors.add(err_key)
                                    desc = f"Missing node / T-junction at ({pt.x():.4f}, {pt.y():.4f}) in FID {featA.id()} (shared with FID {cand_id})"
                                    errors.append(TopologyError(
                                        'Missing Node / Line Intersection', [featA.id(), cand_id], desc,
                                        pt.x(), pt.y(), QgsGeometry.fromPointXY(pt)
                                    ))

                    # 3. Proper Line-Line Crossing Intersections
                    if bA.intersects(bB):
                        inter = bA.intersection(bB)
                        if not inter.isEmpty():
                            inter_pts = []
                            if inter.type() == QgsWkbTypes.GeometryType.PointGeometry:
                                if inter.isMultipart():
                                    inter_pts.extend(inter.asMultiPoint())
                                else:
                                    inter_pts.append(inter.asPoint())
                            elif inter.type() == QgsWkbTypes.GeometryType.LineGeometry:
                                plines = inter.asMultiPolyline() if inter.isMultipart() else [inter.asPolyline()]
                                for pl in plines:
                                    if pl:
                                        inter_pts.append(pl[0])
                                        inter_pts.append(pl[-1])
                            elif inter.isMultipart():
                                for part in inter.asGeometryCollection():
                                    if part.type() == QgsWkbTypes.GeometryType.PointGeometry:
                                        inter_pts.append(part.asPoint())
                                    elif part.type() == QgsWkbTypes.GeometryType.LineGeometry:
                                        pl = part.asPolyline()
                                        if pl:
                                            inter_pts.append(pl[0])
                                            inter_pts.append(pl[-1])

                            for ipt in inter_pts:
                                in_A = any(ipt.distance(pA) <= node_tol for pA in vA)
                                in_B = any(ipt.distance(pB) <= node_tol for pB in vB)
                                if not in_A and not in_B:
                                    err_key_cross = (min(featA.id(), cand_id), max(featA.id(), cand_id), round(ipt.x(), 4), round(ipt.y(), 4))
                                    if err_key_cross not in seen_node_errors:
                                        seen_node_errors.add(err_key_cross)
                                        desc = f"Line intersection without node at ({ipt.x():.4f}, {ipt.y():.4f}) between FID {featA.id()} and FID {cand_id}"
                                        errors.append(TopologyError(
                                            'Missing Node / Line Intersection', [featA.id(), cand_id], desc,
                                            ipt.x(), ipt.y(), QgsGeometry.fromPointXY(ipt)
                                        ))

        return errors

    def run_cross_layer_checks(self, main_features, main_layer, other_layers_features, options: dict, progress_callback=None, target_fids=None):
        errors = []
        target_set = set(target_fids) if target_fids is not None else None
        total_count = len(main_features)
        if total_count == 0:
            return errors

        # Pre-build spatial index for each other layer
        spatial_indexes = {}
        for layer_id, (layer, feats) in other_layers_features.items():
            sp_idx = QgsSpatialIndex()
            feats_map = {}
            for f in feats:
                feats_map[f.id()] = f
                if f.geometry() and not f.geometry().isEmpty():
                    sp_idx.addFeature(f)
            spatial_indexes[layer_id] = (layer, sp_idx, feats_map)

        for idx, feat_main in enumerate(main_features):
            if target_set is not None and feat_main.id() not in target_set:
                continue
            if progress_callback:
                progress_callback(int((idx / total_count) * 100))

            geom_main = feat_main.geometry()
            if not geom_main or geom_main.isEmpty():
                continue

            # 1. Cross-Layer Overlap Check
            if options.get('check_cross_overlaps', True):
                tol = options.get('cross_overlap_tolerance', 0.0001)
                for layer_id, (layer_other, sp_idx, feats_map) in spatial_indexes.items():
                    candidates = sp_idx.intersects(geom_main.boundingBox())
                    for c_id in candidates:
                        feat_other = feats_map.get(c_id)
                        if not feat_other or not feat_other.geometry() or feat_other.geometry().isEmpty():
                            continue
                        
                        geom_other = feat_other.geometry()
                        if geom_main.boundingBox().intersects(geom_other.boundingBox()):
                            if geom_main.intersects(geom_other):
                                inter = geom_main.intersection(geom_other)
                                if not inter.isEmpty() and inter.area() > tol:
                                    centroid = inter.centroid().asPoint() if not inter.centroid().isEmpty() else geom_main.centroid().asPoint()
                                    desc = f"Overlaps with FID {c_id} in layer '{layer_other.name()}' (Area: {inter.area():.4f} sq units)"
                                    feature_layers = [main_layer, layer_other]
                                    errors.append(TopologyError(
                                        'Cross-Layer Overlap', 
                                        [feat_main.id(), c_id], 
                                        desc, 
                                        centroid.x(), 
                                        centroid.y(), 
                                        inter,
                                        feature_layers=feature_layers
                                    ))

            # 2. Cross-Layer Gap Check
            if options.get('check_cross_gaps', True):
                gap_tol = options.get('cross_gap_tolerance', 0.000001)
                for layer_id, (layer_other, sp_idx, feats_map) in spatial_indexes.items():
                    bbox_expanded = geom_main.boundingBox()
                    bbox_expanded.grow(max(gap_tol * 2.0, 1.0))
                    candidates = sp_idx.intersects(bbox_expanded)
                    for c_id in candidates:
                        feat_other = feats_map.get(c_id)
                        if not feat_other or not feat_other.geometry() or feat_other.geometry().isEmpty():
                            continue
                        
                        geom_other = feat_other.geometry()
                        rectA = geom_main.boundingBox()
                        rectB = geom_other.boundingBox()
                        dx = max(0.0, rectA.xMinimum() - rectB.xMaximum(), rectB.xMinimum() - rectA.xMaximum())
                        dy = max(0.0, rectA.yMinimum() - rectB.yMaximum(), rectB.yMinimum() - rectA.yMaximum())
                        if math.hypot(dx, dy) > gap_tol:
                            continue

                        if not geom_main.intersects(geom_other) and not geom_main.touches(geom_other):
                            dist = geom_main.distance(geom_other)
                            if 0.0 < dist <= gap_tol:
                                gap_geom = geom_main.shortestLine(geom_other)
                                if not gap_geom.isEmpty():
                                    cent = gap_geom.centroid().asPoint() if not gap_geom.centroid().isEmpty() else QgsPointXY(0,0)
                                    mid_x = cent.x()
                                    mid_y = cent.y()
                                else:
                                    ptA = geom_main.centroid().asPoint()
                                    ptB = geom_other.centroid().asPoint()
                                    mid_x = (ptA.x() + ptB.x()) / 2.0
                                    mid_y = (ptA.y() + ptB.y()) / 2.0
                                desc = f"Unmapped Gap between main FID {feat_main.id()} and FID {c_id} in layer '{layer_other.name()}' (Distance: {dist:.6f} units)"
                                feature_layers = [main_layer, layer_other]
                                errors.append(TopologyError(
                                    'Cross-Layer Gap / Sliver Void', 
                                    [feat_main.id(), c_id], 
                                    desc, 
                                    mid_x, 
                                    mid_y, 
                                    gap_geom,
                                    feature_layers=feature_layers
                                ))

            # 3. Cross-Layer Missing Node / Line Intersection Check
            if options.get('check_cross_missing_nodes', True):
                cross_node_tol = options.get('cross_missing_node_tolerance', 0.1)
                lines_m = []
                pts_m = []
                poly_list_m = geom_main.asMultiPolygon() if geom_main.isMultipart() else [geom_main.asPolygon()]
                for p in poly_list_m:
                    for ring in p:
                        lines_m.append(ring)
                        pts_m.extend(ring[:-1] if (len(ring) > 1 and ring[0] == ring[-1]) else ring)
                b_main = QgsGeometry.fromMultiPolylineXY(lines_m) if lines_m else None

                if b_main:
                    for layer_id, (layer_other, sp_idx, feats_map) in spatial_indexes.items():
                        bbox_expanded = geom_main.boundingBox()
                        bbox_expanded.grow(max(cross_node_tol * 2.0, 0.5))
                        candidates = sp_idx.intersects(bbox_expanded)
                        for c_id in candidates:
                            feat_other = feats_map.get(c_id)
                            if not feat_other or not feat_other.geometry() or feat_other.geometry().isEmpty():
                                continue
                            geom_other = feat_other.geometry()
                            lines_o = []
                            pts_o = []
                            poly_list_o = geom_other.asMultiPolygon() if geom_other.isMultipart() else [geom_other.asPolygon()]
                            for p in poly_list_o:
                                for ring in p:
                                    lines_o.append(ring)
                                    pts_o.extend(ring[:-1] if (len(ring) > 1 and ring[0] == ring[-1]) else ring)
                            b_other = QgsGeometry.fromMultiPolylineXY(lines_o) if lines_o else None
                            if not b_other:
                                continue

                            # Check vertices of other on main boundary
                            for pt in pts_o:
                                if b_main.distance(QgsGeometry.fromPointXY(pt)) <= cross_node_tol:
                                    if not any(pt.distance(pm) <= cross_node_tol for pm in pts_m):
                                        desc = f"Missing node in main FID {feat_main.id()} at ({pt.x():.4f}, {pt.y():.4f}) matching vertex from layer '{layer_other.name()}' FID {c_id}"
                                        errors.append(TopologyError(
                                            'Cross-Layer Missing Node / Line Intersection',
                                            [feat_main.id(), c_id],
                                            desc,
                                            pt.x(),
                                            pt.y(),
                                            QgsGeometry.fromPointXY(pt),
                                            feature_layers=[main_layer, layer_other]
                                        ))

                            # Check vertices of main on other boundary
                            for pt in pts_m:
                                if b_other.distance(QgsGeometry.fromPointXY(pt)) <= cross_node_tol:
                                    if not any(pt.distance(po) <= cross_node_tol for po in pts_o):
                                        desc = f"Missing node in layer '{layer_other.name()}' FID {c_id} at ({pt.x():.4f}, {pt.y():.4f}) matching vertex from main FID {feat_main.id()}"
                                        errors.append(TopologyError(
                                            'Cross-Layer Missing Node / Line Intersection',
                                            [feat_main.id(), c_id],
                                            desc,
                                            pt.x(),
                                            pt.y(),
                                            QgsGeometry.fromPointXY(pt),
                                            feature_layers=[main_layer, layer_other]
                                        ))
        return errors

    def run_checks_for_features(self, layer: QgsVectorLayer, feature_ids: list, options: dict):
        """Run topology checks selectively for specific feature IDs."""
        if not layer or not layer.isValid() or not feature_ids:
            return []

        # Run checks only targeting the selected feature IDs to maximize processing speed!
        return self.run_checks(layer, options, target_fids=feature_ids)


class TopologyFixer:
    """Handles editing operations on layers to resolve topological errors."""

    @staticmethod
    def fix_invalid_geometry(layer, fid):
        feat = layer.getFeature(fid)
        if not feat.isValid():
            return False
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            return False
        new_geom = geom.makeValid()
        if new_geom and not new_geom.isEmpty():
            res = new_geom.coerceToType(layer.wkbType())
            coerced_geom = res[0] if isinstance(res, list) else res
            if coerced_geom and not coerced_geom.isEmpty():
                return layer.changeGeometry(fid, coerced_geom)
        return False

    @staticmethod
    def fix_duplicate_geometry(layer, fid):
        return layer.deleteFeature(fid)

    @staticmethod
    def fix_multipart_geometry(layer, fid):
        feat = layer.getFeature(fid)
        if not feat.isValid() or not feat.geometry().isMultipart():
            return False
        geom = feat.geometry()
        polygon_list = geom.asMultiPolygon()
        new_features = []
        for poly in polygon_list:
            new_feat = QgsFeature(layer.fields())
            geom_part = QgsGeometry.fromPolygonXY(poly)
            res = geom_part.coerceToType(layer.wkbType())
            coerced_geom = res[0] if isinstance(res, list) else res
            new_feat.setGeometry(coerced_geom)
            new_feat.setAttributes(feat.attributes())
            new_features.append(new_feat)

        if new_features:
            res_add = layer.addFeatures(new_features)
            success = res_add[0] if isinstance(res_add, tuple) else res_add
            if success:
                return layer.deleteFeature(fid)
        return False

    @staticmethod
    def fix_spike_geometry(layer, fid, location_x, location_y):
        feat = layer.getFeature(fid)
        if not feat.isValid():
            return False
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            return False
        vertex_idx = -1
        min_dist = 0.0001
        for idx in range(geom.constGet().vertexCount()):
            pt = geom.vertexAt(idx)
            dist = QgsPointXY(pt).distance(QgsPointXY(location_x, location_y))
            if dist < min_dist:
                min_dist = dist
                vertex_idx = idx

        if vertex_idx != -1:
            if geom.deleteVertex(vertex_idx):
                res = geom.coerceToType(layer.wkbType())
                coerced_geom = res[0] if isinstance(res, list) else res
                if coerced_geom and not coerced_geom.isEmpty():
                    return layer.changeGeometry(fid, coerced_geom)
        return False

    @staticmethod
    def fix_overlap_geometry(layer, fid1, fid2):
        feat1 = layer.getFeature(fid1)
        feat2 = layer.getFeature(fid2)
        if not feat1.isValid() or not feat2.isValid():
            return False

        smaller_feat = feat1 if feat1.geometry().area() < feat2.geometry().area() else feat2
        larger_feat = feat2 if smaller_feat.id() == feat1.id() else feat1

        new_geom = smaller_feat.geometry().difference(larger_feat.geometry())
        if new_geom and not new_geom.isEmpty():
            res = new_geom.coerceToType(layer.wkbType())
            coerced_geom = res[0] if isinstance(res, list) else res
            if coerced_geom and not coerced_geom.isEmpty():
                return layer.changeGeometry(smaller_feat.id(), coerced_geom)
        return False

    @staticmethod
    def fix_sliver_geometry(layer, fid):
        sliver_feat = layer.getFeature(fid)
        if not sliver_feat.isValid():
            return False
        sliver_geom = sliver_feat.geometry()
        if not sliver_geom or sliver_geom.isEmpty():
            return False

        spatial_index = QgsSpatialIndex(layer.getFeatures())
        candidate_ids = spatial_index.intersects(sliver_geom.boundingBox())

        longest_boundary_len = 0.0
        best_neighbor_id = None
        for cand_id in candidate_ids:
            if cand_id == fid:
                continue
            neighbor_feat = layer.getFeature(cand_id)
            if not neighbor_feat.isValid():
                continue
            neighbor_geom = neighbor_feat.geometry()
            if not neighbor_geom or neighbor_geom.isEmpty():
                continue

            inter = sliver_geom.intersection(neighbor_geom)
            if not inter.isEmpty():
                boundary_len = inter.length()
                if boundary_len > longest_boundary_len:
                    longest_boundary_len = boundary_len
                    best_neighbor_id = cand_id

        if best_neighbor_id is not None:
            neighbor_feat = layer.getFeature(best_neighbor_id)
            new_geom = neighbor_feat.geometry().combine(sliver_geom)
            if new_geom and not new_geom.isEmpty():
                res = new_geom.coerceToType(layer.wkbType())
                coerced_geom = res[0] if isinstance(res, list) else res
                if coerced_geom and not coerced_geom.isEmpty():
                    if layer.changeGeometry(best_neighbor_id, coerced_geom):
                        return layer.deleteFeature(fid)
        return False

    @staticmethod
    def fix_overshoot_geometry(layer, fid):
        feat = layer.getFeature(fid)
        if not feat.isValid():
            return False
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            return False
        valid_geom = geom.makeValid()
        if valid_geom and not valid_geom.isEmpty():
            res = valid_geom.coerceToType(layer.wkbType())
            coerced_geom = res[0] if isinstance(res, list) else res
            if coerced_geom and not coerced_geom.isEmpty():
                return layer.changeGeometry(fid, coerced_geom)
        return False

    @staticmethod
    def fix_missing_node(layer, fid, location_x, location_y, tolerance=0.001):
        feat = layer.getFeature(fid)
        if not feat.isValid():
            return False
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            return False
        pt = QgsPointXY(location_x, location_y)

        poly_list = geom.asMultiPolygon() if geom.isMultipart() else [geom.asPolygon()]
        new_polys = []
        inserted = False

        for poly in poly_list:
            new_poly = []
            for ring in poly:
                new_ring = []
                pts = ring[:-1] if (len(ring) > 1 and ring[0] == ring[-1]) else ring
                n = len(pts)
                ring_inserted = False
                for i in range(n):
                    p1 = pts[i]
                    p2 = pts[(i + 1) % n]
                    new_ring.append(p1)

                    if p1.distance(pt) <= tolerance:
                        continue

                    seg_geom = QgsGeometry.fromPolylineXY([p1, p2])
                    if not ring_inserted and not inserted and seg_geom.distance(QgsGeometry.fromPointXY(pt)) <= tolerance:
                        if p2.distance(pt) > tolerance:
                            new_ring.append(pt)
                            ring_inserted = True
                            inserted = True
                new_ring.append(new_ring[0])
                new_poly.append(new_ring)
            new_polys.append(new_poly)

        if inserted:
            new_geom = QgsGeometry.fromMultiPolygonXY(new_polys) if geom.isMultipart() else QgsGeometry.fromPolygonXY(new_polys[0])
            res = new_geom.coerceToType(layer.wkbType())
            coerced_geom = res[0] if isinstance(res, list) else res
            if coerced_geom and not coerced_geom.isEmpty():
                return layer.changeGeometry(fid, coerced_geom)
        return False

    @staticmethod
    def fix_cross_layer_overlap(main_layer, main_fid, other_layer, other_fid):
        main_feat = main_layer.getFeature(main_fid)
        other_feat = other_layer.getFeature(other_fid)
        if not main_feat.isValid() or not other_feat.isValid():
            return False

        new_geom = main_feat.geometry().difference(other_feat.geometry())
        if new_geom and not new_geom.isEmpty():
            res = new_geom.coerceToType(main_layer.wkbType())
            coerced_geom = res[0] if isinstance(res, list) else res
            if coerced_geom and not coerced_geom.isEmpty():
                return main_layer.changeGeometry(main_fid, coerced_geom)
        return False


class TopologyCheckTask(QgsTask):
    """Task to run topology checks asynchronously in a background thread."""
    def __init__(self, layer, options, target_fids, callback, mode='single', other_layers_data=None):
        super().__init__("Running Topology Check", QgsTask.Flags())
        self.mode = mode
        self.layer = layer
        self.features = [QgsFeature(f) for f in layer.getFeatures()]
        self.options = options
        self.target_fids = target_fids
        self.callback = callback
        self.errors = []
        self.engine = TopologyEngine()
        
        # Store other layers data as a dictionary of (layer_ref, list_of_copied_features)
        self.other_layers_data = {}
        if other_layers_data:
            for l_id, l_ref in other_layers_data.items():
                self.other_layers_data[l_id] = (l_ref, [QgsFeature(f) for f in l_ref.getFeatures()])

    def run(self):
        try:
            # Background thread execution
            def progress_cb(progress):
                self.setProgress(progress)
                if self.isCanceled():
                    return False
                return True
            
            if self.mode == 'single':
                self.errors = self.engine.run_checks(
                    self.features, self.options, 
                    progress_callback=progress_cb, 
                    target_fids=self.target_fids
                )
            else:
                self.errors = self.engine.run_cross_layer_checks(
                    self.features, self.layer, self.other_layers_data, self.options,
                    progress_callback=progress_cb, 
                    target_fids=self.target_fids
                )
            return True
        except Exception as e:
            print(f"Error in TopologyCheckTask: {str(e)}")
            return False

    def finished(self, result):
        # Main thread callback
        self.callback(self.errors, result)


class TopologyCheckerDialog(QDialog):
    """UI Dialog for Layer selection, processing options, and error inspection."""

    def __init__(self, parent=None, iface=None):
        super().__init__(parent or (iface.mainWindow() if iface else None))
        self.iface = iface
        self.setWindowTitle("Comprehensive Topology Checker")
        self.resize(920, 720)
        self.engine = TopologyEngine()
        self.errors = []
        self.rubber_band = None
        self.vertex_marker = None
        self.preview_rubber_bands = []
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Tab Widget
        self.tab_widget = QTabWidget()
        
        # ==========================================
        # TAB 1: Single Layer Check
        # ==========================================
        tab1_widget = QWidget()
        tab1_layout = QVBoxLayout(tab1_widget)
        
        # Layer Selection Box
        layer_group = QGroupBox("Layer Selection")
        layer_layout = QFormLayout()
        self.layer_cb = QgsMapLayerComboBox()
        self.layer_cb.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        layer_layout.addRow("Target Polygon Layer:", self.layer_cb)
        layer_group.setLayout(layer_layout)
        tab1_layout.addWidget(layer_group)

        # Rules and Settings (Balanced Grid Layout)
        rules_group = QGroupBox("Topology Rules & Tolerances")
        rules_layout = QVBoxLayout()
        
        # Select/Deselect All buttons layout
        sel_btn_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setToolTip("Check and enable all topology validation rules")
        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.setToolTip("Uncheck and disable all topology validation rules")
        self.btn_select_all.setStyleSheet("padding: 3px 8px; max-width: 100px;")
        self.btn_deselect_all.setStyleSheet("padding: 3px 8px; max-width: 100px;")
        self.btn_select_all.clicked.connect(self.select_all_rules)
        self.btn_deselect_all.clicked.connect(self.deselect_all_rules)
        sel_btn_layout.addWidget(self.btn_select_all)
        sel_btn_layout.addWidget(self.btn_deselect_all)
        sel_btn_layout.addStretch()
        rules_layout.addLayout(sel_btn_layout)
        
        columns_layout = QHBoxLayout()
        
        # Column 1 (5 Rules: Validity, Spikes, Prolonged, Overlaps, Missing Nodes)
        col1_widget = QWidget()
        col1_vbox = QVBoxLayout(col1_widget)
        col1_vbox.setContentsMargins(5, 5, 5, 5)
        col1_vbox.setSpacing(8)
        
        self.cb_validity = QCheckBox("Check Invalid Geometry / Self-Intersections")
        self.cb_validity.setChecked(True)
        self.cb_validity.setToolTip("Identify OGC / GEOS invalid geometries (e.g., self-intersecting rings, bowties, unclosed rings)")
        row_val = QHBoxLayout()
        row_val.addWidget(self.cb_validity)
        row_val.addStretch()
        col1_vbox.addLayout(row_val)
        
        self.cb_spikes = QCheckBox("Check Spikes & Acute Angles (deg ≤):")
        self.cb_spikes.setChecked(True)
        self.cb_spikes.setToolTip("Detect acute zig-zag vertices (spikes) where interior angle is less than or equal to threshold")
        self.spike_angle_spin = QDoubleSpinBox()
        self.spike_angle_spin.setRange(0.1, 90.0)
        self.spike_angle_spin.setDecimals(1)
        self.spike_angle_spin.setValue(15.0)
        self.spike_angle_spin.setFixedWidth(85)
        self.spike_angle_spin.setToolTip("Spike angle threshold in degrees (angles ≤ this value are flagged as spikes)")
        self.cb_spikes.toggled.connect(self.spike_angle_spin.setEnabled)
        row_spike = QHBoxLayout()
        row_spike.addWidget(self.cb_spikes)
        row_spike.addWidget(self.spike_angle_spin)
        row_spike.addStretch()
        col1_vbox.addLayout(row_spike)
        
        self.cb_prolonged_edges = QCheckBox("Check Prolonged Edges / Overshoots")
        self.cb_prolonged_edges.setChecked(True)
        self.cb_prolonged_edges.setToolTip("Detect degenerate overshoots where an edge doubles back upon itself with zero/near-zero enclosed area")
        row_pro = QHBoxLayout()
        row_pro.addWidget(self.cb_prolonged_edges)
        row_pro.addStretch()
        col1_vbox.addLayout(row_pro)
        
        self.cb_overlaps = QCheckBox("Check Polygon Overlaps (area ≥):")
        self.cb_overlaps.setChecked(True)
        self.cb_overlaps.setToolTip("Detect overlapping polygon areas within the layer exceeding the specified area threshold")
        self.overlap_spin = QDoubleSpinBox()
        self.overlap_spin.setRange(0.000001, 1000000.0)
        self.overlap_spin.setDecimals(4)
        self.overlap_spin.setValue(0.0001)
        self.overlap_spin.setFixedWidth(85)
        self.overlap_spin.setToolTip("Minimum overlapping area threshold in square layer units")
        self.cb_overlaps.toggled.connect(self.overlap_spin.setEnabled)
        row_overlap = QHBoxLayout()
        row_overlap.addWidget(self.cb_overlaps)
        row_overlap.addWidget(self.overlap_spin)
        row_overlap.addStretch()
        col1_vbox.addLayout(row_overlap)

        self.cb_missing_nodes = QCheckBox("Check Missing Nodes / Intersections (tol):")
        self.cb_missing_nodes.setChecked(True)
        self.cb_missing_nodes.setToolTip("Detect T-junctions and line intersections where a boundary vertex/edge touches/crosses another polygon without a node")
        self.missing_node_spin = QDoubleSpinBox()
        self.missing_node_spin.setRange(0.000001, 1000000.0)
        self.missing_node_spin.setDecimals(4)
        self.missing_node_spin.setValue(0.1)
        self.missing_node_spin.setFixedWidth(85)
        self.missing_node_spin.setToolTip("Maximum distance tolerance (in layer units) to detect and snap missing nodes / T-junctions")
        self.cb_missing_nodes.toggled.connect(self.missing_node_spin.setEnabled)
        row_mn = QHBoxLayout()
        row_mn.addWidget(self.cb_missing_nodes)
        row_mn.addWidget(self.missing_node_spin)
        row_mn.addStretch()
        col1_vbox.addLayout(row_mn)
        col1_vbox.addStretch()
        
        columns_layout.addWidget(col1_widget)
        
        # Column 2 (5 Rules: Gaps, Enclosed Holes, Duplicates, Multipart, Slivers)
        col2_widget = QWidget()
        col2_vbox = QVBoxLayout(col2_widget)
        col2_vbox.setContentsMargins(5, 5, 5, 5)
        col2_vbox.setSpacing(8)
        
        self.cb_gaps = QCheckBox("Check Sliver Gaps (dist ≤):")
        self.cb_gaps.setChecked(True)
        self.cb_gaps.setToolTip("Detect narrow unmapped sliver gaps between adjacent polygons within the distance threshold")
        self.gap_spin = QDoubleSpinBox()
        self.gap_spin.setRange(0.000001, 1000000.0)
        self.gap_spin.setDecimals(4)
        self.gap_spin.setValue(1.0)
        self.gap_spin.setFixedWidth(85)
        self.gap_spin.setToolTip("Maximum gap distance limit (in layer units) between adjacent polygons")
        self.cb_gaps.toggled.connect(self.gap_spin.setEnabled)
        row_gap = QHBoxLayout()
        row_gap.addWidget(self.cb_gaps)
        row_gap.addWidget(self.gap_spin)
        row_gap.addStretch()
        col2_vbox.addLayout(row_gap)
        
        self.cb_enclosed_gaps = QCheckBox("Check Enclosed Holes / Voids (No Gaps)")
        self.cb_enclosed_gaps.setChecked(True)
        self.cb_enclosed_gaps.setToolTip("Detect completely enclosed unmapped holes or voids surrounded by contiguous polygons (must not have internal gaps)")
        row_enc = QHBoxLayout()
        row_enc.addWidget(self.cb_enclosed_gaps)
        row_enc.addStretch()
        col2_vbox.addLayout(row_enc)
        
        self.cb_duplicates = QCheckBox("Check Duplicate Geometries")
        self.cb_duplicates.setChecked(True)
        self.cb_duplicates.setToolTip("Detect identical duplicate polygon geometries sharing identical coordinates and boundaries")
        row_dup = QHBoxLayout()
        row_dup.addWidget(self.cb_duplicates)
        row_dup.addStretch()
        col2_vbox.addLayout(row_dup)
        
        self.cb_multipart = QCheckBox("Check Multipart Geometries")
        self.cb_multipart.setChecked(True)
        self.cb_multipart.setToolTip("Detect multi-polygon features containing disjoint parts instead of clean single-part polygons")
        row_multi = QHBoxLayout()
        row_multi.addWidget(self.cb_multipart)
        row_multi.addStretch()
        col2_vbox.addLayout(row_multi)
        
        self.cb_min_area = QCheckBox("Check Micro-Polygons / Slivers (area ≤):")
        self.cb_min_area.setChecked(True)
        self.cb_min_area.setToolTip("Detect tiny micro-polygons or sliver polygons whose area is below the minimum area threshold")
        self.min_area_spin = QDoubleSpinBox()
        self.min_area_spin.setRange(0.000001, 1000000.0)
        self.min_area_spin.setDecimals(4)
        self.min_area_spin.setValue(0.01)
        self.min_area_spin.setFixedWidth(85)
        self.min_area_spin.setToolTip("Minimum polygon area threshold in square layer units")
        self.cb_min_area.toggled.connect(self.min_area_spin.setEnabled)
        row_min_area = QHBoxLayout()
        row_min_area.addWidget(self.cb_min_area)
        row_min_area.addWidget(self.min_area_spin)
        row_min_area.addStretch()
        col2_vbox.addLayout(row_min_area)
        col2_vbox.addStretch()
        
        columns_layout.addWidget(col2_widget)
        rules_layout.addLayout(columns_layout)
        rules_group.setLayout(rules_layout)
        tab1_layout.addWidget(rules_group)
        
        self.tab_widget.addTab(tab1_widget, "Single Layer Checks")

        # ==========================================
        # TAB 2: Cross-Layer Check
        # ==========================================
        tab2_widget = QWidget()
        tab2_layout = QVBoxLayout(tab2_widget)
        
        # Main Layer Combobox
        main_layer_group = QGroupBox("Main Layer")
        main_layer_layout = QFormLayout()
        self.main_layer_cb = QgsMapLayerComboBox()
        self.main_layer_cb.setFilters(QgsMapLayerProxyModel.Filter.PolygonLayer)
        self.main_layer_cb.setToolTip("Select the primary layer to validate against other layers")
        self.main_layer_cb.currentIndexChanged.connect(self.populate_other_layers_list)
        main_layer_layout.addRow("Select Main Layer:", self.main_layer_cb)
        main_layer_group.setLayout(main_layer_layout)
        tab2_layout.addWidget(main_layer_group)
        
        # Other Layers List Widget
        other_layers_group = QGroupBox("Compare Against Layer(s)")
        other_layers_layout = QVBoxLayout()
        self.other_layers_list = QListWidget()
        self.other_layers_list.setToolTip("Check all polygon layers you want to compare against the Main Layer")
        other_layers_layout.addWidget(self.other_layers_list)
        other_layers_group.setLayout(other_layers_layout)
        tab2_layout.addWidget(other_layers_group)
        
        # Cross Layer Rules
        cross_rules_group = QGroupBox("Cross-Layer Rules & Tolerances")
        cross_rules_layout = QVBoxLayout(cross_rules_group)
        cross_rules_layout.setSpacing(8)
        
        self.cb_cross_overlaps = QCheckBox("Check Cross-Layer Overlaps (area ≥):")
        self.cb_cross_overlaps.setChecked(True)
        self.cb_cross_overlaps.setToolTip("Detect spatial overlaps between Main Layer features and compared layer features")
        self.cross_overlap_spin = QDoubleSpinBox()
        self.cross_overlap_spin.setRange(0.000001, 1000000.0)
        self.cross_overlap_spin.setDecimals(4)
        self.cross_overlap_spin.setValue(0.0001)
        self.cross_overlap_spin.setFixedWidth(85)
        self.cross_overlap_spin.setToolTip("Minimum cross-layer overlapping area threshold in square layer units")
        self.cb_cross_overlaps.toggled.connect(self.cross_overlap_spin.setEnabled)
        row_co = QHBoxLayout()
        row_co.addWidget(self.cb_cross_overlaps)
        row_co.addWidget(self.cross_overlap_spin)
        row_co.addStretch()
        cross_rules_layout.addLayout(row_co)
        
        self.cb_cross_gaps = QCheckBox("Check Cross-Layer Gaps (dist ≤):")
        self.cb_cross_gaps.setChecked(True)
        self.cb_cross_gaps.setToolTip("Detect unmapped gaps / voids between Main Layer boundaries and compared layers")
        self.cross_gap_spin = QDoubleSpinBox()
        self.cross_gap_spin.setRange(0.000001, 1000000.0)
        self.cross_gap_spin.setDecimals(4)
        self.cross_gap_spin.setValue(1.0)
        self.cross_gap_spin.setFixedWidth(85)
        self.cross_gap_spin.setToolTip("Maximum gap distance limit (in layer units) between Main Layer and other layers")
        self.cb_cross_gaps.toggled.connect(self.cross_gap_spin.setEnabled)
        row_cg = QHBoxLayout()
        row_cg.addWidget(self.cb_cross_gaps)
        row_cg.addWidget(self.cross_gap_spin)
        row_cg.addStretch()
        cross_rules_layout.addLayout(row_cg)

        self.cb_cross_missing_nodes = QCheckBox("Check Cross-Layer Missing Nodes / Intersections (tol):")
        self.cb_cross_missing_nodes.setChecked(True)
        self.cb_cross_missing_nodes.setToolTip("Detect T-junctions and boundary crossings between Main Layer and compared layers without matching nodes")
        self.cross_missing_node_spin = QDoubleSpinBox()
        self.cross_missing_node_spin.setRange(0.000001, 1000000.0)
        self.cross_missing_node_spin.setDecimals(4)
        self.cross_missing_node_spin.setValue(0.1)
        self.cross_missing_node_spin.setFixedWidth(85)
        self.cross_missing_node_spin.setToolTip("Maximum distance tolerance (in layer units) for cross-layer missing nodes")
        self.cb_cross_missing_nodes.toggled.connect(self.cross_missing_node_spin.setEnabled)
        row_cmn = QHBoxLayout()
        row_cmn.addWidget(self.cb_cross_missing_nodes)
        row_cmn.addWidget(self.cross_missing_node_spin)
        row_cmn.addStretch()
        cross_rules_layout.addLayout(row_cmn)
        
        tab2_layout.addWidget(cross_rules_group)
        self.tab_widget.addTab(tab2_widget, "Cross-Layer Checks")
        
        # Add tab widget to main layout
        layout.addWidget(self.tab_widget)
        
        # Connect layers added/removed to list updates
        QgsProject.instance().layersAdded.connect(self.populate_other_layers_list)
        QgsProject.instance().layersRemoved.connect(self.populate_other_layers_list)
        
        # Call initial populator
        self.populate_other_layers_list()

        # Row 1: Primary Action Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_run = QPushButton("Run Topology Check")
        self.btn_run.setToolTip("Execute selected topology rule checks on the target layer")
        self.btn_run.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_run.clicked.connect(self.run_check)
        btn_layout.addWidget(self.btn_run)
        
        self.btn_recheck_selected = QPushButton("Re-check Selected")
        self.btn_recheck_selected.setToolTip("Re-validate only the features corresponding to selected error rows in the table")
        self.btn_recheck_selected.setStyleSheet("background-color: #5cb85c; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_recheck_selected.clicked.connect(self.recheck_selected_error)
        self.btn_recheck_selected.setEnabled(False)
        btn_layout.addWidget(self.btn_recheck_selected)

        self.btn_toggle_highlight = QPushButton("Highlight Errors")
        self.btn_toggle_highlight.setToolTip("Toggle visual highlight markers and polygon outlines on the map canvas for all detected errors")
        self.btn_toggle_highlight.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_toggle_highlight.clicked.connect(self.toggle_highlights)
        self.btn_toggle_highlight.setEnabled(False)
        self.highlights_active = False
        btn_layout.addWidget(self.btn_toggle_highlight)

        btn_layout.addStretch()

        self.autofix_cb = QComboBox()
        self.autofix_cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.autofix_cb.addItems(["Auto-Fix Selected", "Auto-Fix All"])
        self.autofix_cb.setFixedWidth(150)
        self.autofix_cb.setToolTip("Choose whether Auto-Fix applies to only selected rows or all detected errors in the layer")
        btn_layout.addWidget(self.autofix_cb)

        self.btn_autofix = QPushButton("Auto-Fix")
        self.btn_autofix.setToolTip("Automatically fix repairable topology errors (spikes, overshoots, overlaps, missing nodes, multipart, duplicates)")
        self.btn_autofix.setStyleSheet("background-color: #f0ad4e; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_autofix.clicked.connect(self.apply_autofix)
        self.btn_autofix.setEnabled(False)
        btn_layout.addWidget(self.btn_autofix)
        
        layout.addLayout(btn_layout)

        # Row 2: Filter, Search & Export Bar
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Type Filter:"))
        self.filter_cb = QComboBox()
        self.filter_cb.addItems([
            "All Error Types",
            "Invalid Geometry",
            "Spike / Acute Vertex",
            "Prolonged Edge / Overshoot",
            "Overlap",
            "Gap / Void",
            "Missing Node / Line Intersection",
            "Duplicate Geometry",
            "Multipart Geometry",
            "Micro Polygon / Sliver"
        ])
        self.filter_cb.setToolTip("Filter error table rows by specific topology error category")
        self.filter_cb.currentTextChanged.connect(self.populate_table)
        filter_layout.addWidget(self.filter_cb)
        
        filter_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by FID, type, or description...")
        self.search_edit.setToolTip("Search error records in real time by Feature ID, error type, or description")
        self.search_edit.textChanged.connect(self.populate_table)
        filter_layout.addWidget(self.search_edit)
        
        filter_layout.addWidget(QLabel("Export:"))
        self.export_cb = QComboBox()
        self.export_cb.addItems(["Export to CSV", "Export to HTML", "Create Error Layer"])
        self.export_cb.setToolTip("Choose export format: CSV spreadsheet, HTML report, or temporary GIS vector layer")
        filter_layout.addWidget(self.export_cb)
        
        self.btn_export = QPushButton("Export")
        self.btn_export.setToolTip("Export the current error list to the chosen format")
        self.btn_export.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold; padding: 5px 12px;")
        self.btn_export.clicked.connect(self.execute_export)
        self.btn_export.setEnabled(False)
        filter_layout.addWidget(self.btn_export)

        self.cb_show_highlights = QCheckBox("Show Highlights")
        self.cb_show_highlights.setChecked(True)
        self.cb_show_highlights.setToolTip("Automatically zoom, pan, and highlight error features on the map canvas when clicking table rows")
        self.cb_show_highlights.stateChanged.connect(self.on_show_highlights_changed)
        filter_layout.addWidget(self.cb_show_highlights)
        
        layout.addLayout(filter_layout)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Status Summary Label
        self.lbl_summary = QLabel("Select layer and click 'Run Topology Check'.")
        self.lbl_summary.setStyleSheet("font-weight: bold;")
        self.lbl_summary.setWordWrap(True)
        layout.addWidget(self.lbl_summary)
        
        # Error Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["#", "Feature ID(s)", "Error Type", "Description", "Location (X, Y)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self.on_table_select)
        self.table.cellDoubleClicked.connect(self.on_table_double_click)
        layout.addWidget(self.table)

        self.all_markers = []
        self.all_rubber_bands = []

    def populate_other_layers_list(self):
        self.other_layers_list.clear()
        main_layer = self.main_layer_cb.currentLayer()
        all_layers = QgsProject.instance().mapLayers().values()
        
        for layer in all_layers:
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry:
                if main_layer and layer.id() == main_layer.id():
                    continue
                item = QListWidgetItem(layer.name())
                item.setData(USER_ROLE, layer.id())
                item.setFlags(item.flags() | ITEM_IS_USER_CHECKABLE)
                item.setCheckState(CHECKED) # default checked
                self.other_layers_list.addItem(item)

    def select_all_rules(self):
        for cb in [self.cb_validity, self.cb_spikes, self.cb_prolonged_edges, self.cb_overlaps,
                   self.cb_gaps, self.cb_enclosed_gaps, self.cb_missing_nodes, self.cb_duplicates, self.cb_multipart, self.cb_min_area]:
            cb.setChecked(True)

    def deselect_all_rules(self):
        for cb in [self.cb_validity, self.cb_spikes, self.cb_prolonged_edges, self.cb_overlaps,
                   self.cb_gaps, self.cb_enclosed_gaps, self.cb_missing_nodes, self.cb_duplicates, self.cb_multipart, self.cb_min_area]:
            cb.setChecked(False)

    def get_options(self):
        return {
            'check_validity': self.cb_validity.isChecked(),
            'check_spikes': self.cb_spikes.isChecked(),
            'spike_angle_threshold': self.spike_angle_spin.value(),
            'check_prolonged_edges': self.cb_prolonged_edges.isChecked(),
            'check_overlaps': self.cb_overlaps.isChecked(),
            'overlap_tolerance': self.overlap_spin.value(),
            'check_gaps': self.cb_gaps.isChecked(),
            'gap_distance_tolerance': self.gap_spin.value(),
            'check_enclosed_gaps': self.cb_enclosed_gaps.isChecked(),
            'check_missing_nodes': self.cb_missing_nodes.isChecked(),
            'missing_node_tolerance': self.missing_node_spin.value(),
            'check_duplicates': self.cb_duplicates.isChecked(),
            'check_multipart': self.cb_multipart.isChecked(),
            'check_min_area': self.cb_min_area.isChecked(),
            'min_area_tolerance': self.min_area_spin.value()
        }

    def on_check_completed(self, errors, success):
        self.progress_bar.setValue(100)
        self.btn_run.setEnabled(True)
        
        if success:
            self.errors = errors
            self.populate_table()
            
            has_errs = len(self.errors) > 0
            self.btn_recheck_selected.setEnabled(has_errs)
            self.btn_autofix.setEnabled(has_errs)
            self.btn_toggle_highlight.setEnabled(has_errs)
            self.btn_export.setEnabled(has_errs)
            
            if self.tab_widget.currentIndex() == 0:
                layer = self.layer_cb.currentLayer()
                self.lbl_summary.setText(f"Inspection Complete: Found {len(self.errors)} topology error(s) in layer '{layer.name()}'.")
            else:
                layer = self.main_layer_cb.currentLayer()
                self.lbl_summary.setText(f"Cross-Layer Inspection Complete: Found {len(self.errors)} error(s) for main layer '{layer.name()}'.")
        else:
            QMessageBox.critical(self, "Error", "Topology checking failed or was cancelled.")
            self.lbl_summary.setText("Inspection failed.")

    def run_check(self):
        if self.tab_widget.currentIndex() == 0:
            layer = self.layer_cb.currentLayer()
            if not layer:
                QMessageBox.warning(self, "Warning", "Please select a valid vector layer.")
                return

            options = self.get_options()

            self.progress_bar.setValue(0)
            self.btn_run.setEnabled(False)
            self.lbl_summary.setText("Running check in background...")
            
            self.check_task = TopologyCheckTask(layer, options, None, self.on_check_completed, mode='single')
            QgsApplication.taskManager().addTask(self.check_task)
        else:
            main_layer = self.main_layer_cb.currentLayer()
            if not main_layer:
                QMessageBox.warning(self, "Warning", "Please select a valid main vector layer.")
                return
            
            # Find selected other layers
            other_layers_data = {}
            for i in range(self.other_layers_list.count()):
                item = self.other_layers_list.item(i)
                if item.checkState() == CHECKED:
                    l_id = item.data(USER_ROLE)
                    layer_ref = QgsProject.instance().mapLayer(l_id)
                    if layer_ref:
                        other_layers_data[l_id] = layer_ref
            
            if not other_layers_data:
                QMessageBox.warning(self, "Warning", "Please select at least one comparison layer.")
                return
                
            options = {
                'check_cross_overlaps': self.cb_cross_overlaps.isChecked(),
                'cross_overlap_tolerance': self.cross_overlap_spin.value(),
                'check_cross_gaps': self.cb_cross_gaps.isChecked(),
                'cross_gap_tolerance': self.cross_gap_spin.value(),
                'check_cross_missing_nodes': self.cb_cross_missing_nodes.isChecked(),
                'cross_missing_node_tolerance': self.cross_missing_node_spin.value()
            }
            
            self.progress_bar.setValue(0)
            self.btn_run.setEnabled(False)
            self.lbl_summary.setText("Running cross-layer check in background...")
            
            self.check_task = TopologyCheckTask(main_layer, options, None, self.on_check_completed, mode='cross', other_layers_data=other_layers_data)
            QgsApplication.taskManager().addTask(self.check_task)

    def toggle_highlights(self):
        if self.highlights_active:
            self.clear_all_canvas_markers()
            self.highlights_active = False
            self.btn_toggle_highlight.setText("Highlight Errors")
            self.btn_toggle_highlight.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 6px;")
        else:
            self.highlight_all_errors()
            self.highlights_active = True
            self.btn_toggle_highlight.setText("Clear Highlights")
            self.btn_toggle_highlight.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold; padding: 6px;")

    def execute_export(self):
        action = self.export_cb.currentText()
        if action == "Export to CSV":
            self.export_csv()
        elif action == "Export to HTML":
            self.export_html()
        elif action == "Create Error Layer":
            self.user_create_error_layer()

    def run_recheck_async(self, layer, fids):
        self.btn_recheck_selected.setEnabled(False)
        self.btn_autofix.setEnabled(False)
        fid_label = f"{len(fids)} features" if len(fids) > 5 else f"feature(s) {', '.join(map(str, fids))}"
        self.lbl_summary.setText(f"Re-checking {fid_label}...")
        
        def on_recheck_completed(errors, success):
            has_errs = len(self.errors) > 0
            self.btn_recheck_selected.setEnabled(has_errs)
            self.btn_autofix.setEnabled(has_errs)
            if success:
                target_set = set(fids)
                self.errors = [e for e in self.errors if not any(fid in target_set for fid in e.feature_ids)]
                self.errors.extend(errors)
                self.populate_table()
                if not errors:
                    fid_msg = f"{len(fids)} features" if len(fids) > 5 else f"Feature ID(s) {', '.join(map(str, fids))}"
                    self.lbl_summary.setText(f"Re-check Complete: {fid_msg} fixed!")
                    QMessageBox.information(self.iface.mainWindow() if (hasattr(self, 'iface') and self.iface) else self, "Feature Fixed", f"{fid_msg} passed successfully!")
                else:
                    self.lbl_summary.setText(f"Re-check Complete: {len(self.errors)} error(s) remaining.")
            else:
                self.lbl_summary.setText("Re-check failed.")
        
        if self.tab_widget.currentIndex() == 0:
            options = self.get_options()
            self.recheck_task = TopologyCheckTask(layer, options, fids, on_recheck_completed, mode='single')
        else:
            # Recheck in cross-layer mode
            other_layers_data = {}
            for i in range(self.other_layers_list.count()):
                item = self.other_layers_list.item(i)
                if item.checkState() == CHECKED:
                    l_id = item.data(USER_ROLE)
                    layer_ref = QgsProject.instance().mapLayer(l_id)
                    if layer_ref:
                        other_layers_data[l_id] = layer_ref
            options = {
                'check_cross_overlaps': self.cb_cross_overlaps.isChecked(),
                'cross_overlap_tolerance': self.cross_overlap_spin.value(),
                'check_cross_gaps': self.cb_cross_gaps.isChecked(),
                'cross_gap_tolerance': self.cross_gap_spin.value(),
                'check_cross_missing_nodes': self.cb_cross_missing_nodes.isChecked(),
                'cross_missing_node_tolerance': self.cross_missing_node_spin.value()
            }
            self.recheck_task = TopologyCheckTask(layer, options, fids, on_recheck_completed, mode='cross', other_layers_data=other_layers_data)
            
        QgsApplication.taskManager().addTask(self.recheck_task)

    def recheck_selected_error(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Info", "Please select an error row in the table to re-check.")
            return
        row = selected_rows[0].row()
        item = self.table.item(row, 0)
        if not item:
            return
        original_idx = item.data(USER_ROLE)
        if original_idx is None or not (0 <= original_idx < len(self.errors)):
            return

        selected_err = self.errors[original_idx]
        fids = selected_err.feature_ids
        layer = self.layer_cb.currentLayer() if self.tab_widget.currentIndex() == 0 else self.main_layer_cb.currentLayer()

        if not layer or not fids:
            return

        self.run_recheck_async(layer, fids)

    def apply_autofix(self):
        mode = self.autofix_cb.currentText()
        if mode == "Auto-Fix Selected":
            self.autofix_selected_error()
        elif mode == "Auto-Fix All":
            self.autofix_all_errors()

    def autofix_selected_error(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Info", "Please select one or more error rows in the table to auto-fix.")
            return

        selected_errors = []
        for s_row in selected_rows:
            row = s_row.row()
            item = self.table.item(row, 0)
            if item:
                original_idx = item.data(USER_ROLE)
                if original_idx is not None and 0 <= original_idx < len(self.errors):
                    selected_errors.append(self.errors[original_idx])

        active_layer = self.layer_cb.currentLayer() if self.tab_widget.currentIndex() == 0 else self.main_layer_cb.currentLayer()
        if not active_layer:
            return

        supported_types = {
            'Invalid Geometry',
            'Duplicate Geometry',
            'Multipart Geometry',
            'Spike / Acute Vertex',
            'Overlap',
            'Micro Polygon / Sliver',
            'Prolonged Edge / Overshoot',
            'Missing Node / Line Intersection',
            'Cross-Layer Overlap',
            'Cross-Layer Missing Node / Line Intersection'
        }

        fixable_errors = [e for e in selected_errors if e.error_type in supported_types]
        if not fixable_errors:
            QMessageBox.warning(self, "No Fixable Errors", "None of the selected errors can be automatically fixed.")
            return

        reply = QMessageBox.question(
            self, "Confirm Bulk Auto-Fix",
            f"Are you sure you want to automatically fix the {len(fixable_errors)} selected error(s)?\nThis will modify the vector layer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_autofix.setEnabled(False)

        fixed_count = 0
        failed_count = 0
        all_affected_fids = []
        edited_layers = set()

        try:
            for err in fixable_errors:
                if err.error_type == 'Cross-Layer Overlap':
                    main_fid = err.feature_ids[0]
                    other_fid = err.feature_ids[1]
                    main_l = err.feature_layers[0] if len(err.feature_layers) > 0 else None
                    other_l = err.feature_layers[1] if len(err.feature_layers) > 1 else None
                    if main_l and other_l:
                        if not main_l.getFeature(main_fid).isValid():
                            fixed_count += 1
                            continue

                        main_l.startEditing()
                        edited_layers.add(main_l)
                        if TopologyFixer.fix_cross_layer_overlap(main_l, main_fid, other_l, other_fid):
                            fixed_count += 1
                            all_affected_fids.append(main_fid)
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1

                elif err.error_type == 'Cross-Layer Missing Node / Line Intersection':
                    main_fid = err.feature_ids[0]
                    main_l = err.feature_layers[0] if len(err.feature_layers) > 0 else None
                    if main_l and main_l.getFeature(main_fid).isValid():
                        main_l.startEditing()
                        edited_layers.add(main_l)
                        if TopologyFixer.fix_missing_node(main_l, main_fid, err.location_x, err.location_y):
                            fixed_count += 1
                            all_affected_fids.append(main_fid)
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1
                else:
                    features_exist = True
                    for fid in err.feature_ids:
                        f = active_layer.getFeature(fid)
                        if not f.isValid():
                            features_exist = False
                            break
                    if not features_exist:
                        fixed_count += 1
                        continue

                    active_layer.startEditing()
                    edited_layers.add(active_layer)
                    if err.error_type == 'Invalid Geometry':
                        if TopologyFixer.fix_invalid_geometry(active_layer, err.feature_ids[0]):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Duplicate Geometry':
                        if TopologyFixer.fix_duplicate_geometry(active_layer, err.feature_ids[0]):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Multipart Geometry':
                        if TopologyFixer.fix_multipart_geometry(active_layer, err.feature_ids[0]):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Spike / Acute Vertex':
                        if TopologyFixer.fix_spike_geometry(active_layer, err.feature_ids[0], err.location_x, err.location_y):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Overlap':
                        if len(err.feature_ids) >= 2:
                            if TopologyFixer.fix_overlap_geometry(active_layer, err.feature_ids[0], err.feature_ids[1]):
                                fixed_count += 1
                                all_affected_fids.extend(err.feature_ids)
                            else:
                                failed_count += 1
                        else:
                            failed_count += 1

                    elif err.error_type == 'Micro Polygon / Sliver':
                        if TopologyFixer.fix_sliver_geometry(active_layer, err.feature_ids[0]):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Prolonged Edge / Overshoot':
                        if TopologyFixer.fix_overshoot_geometry(active_layer, err.feature_ids[0]):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Missing Node / Line Intersection':
                        target_fid = err.feature_ids[0]
                        if TopologyFixer.fix_missing_node(active_layer, target_fid, err.location_x, err.location_y):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

            if fixed_count > 0:
                msg = f"Auto-fixed {fixed_count} error(s) in edit buffer."
                if failed_count > 0:
                    msg += f" (Failed to fix {failed_count} error(s))."
                msg += "\n\nNote: The fixes have been applied in edit mode. Please review them and save or discard layer changes manually in QGIS."
                QMessageBox.information(self, "Success", msg)
                self.recheck_after_autofix(active_layer, list(set(all_affected_fids)))
            else:
                for l in edited_layers:
                    l.rollBack()
                QMessageBox.warning(self, "Error", "Failed to fix the selected error(s) automatically.")
        except Exception as e:
            for l in edited_layers:
                l.rollBack()
            QMessageBox.critical(self, "Error", f"An error occurred during auto-fix: {str(e)}")
        finally:
            has_errs = len(self.errors) > 0
            self.btn_autofix.setEnabled(has_errs)

    def autofix_all_errors(self):
        filtered = self.get_filtered_errors()
        if not filtered:
            QMessageBox.information(self, "Info", "No errors to auto-fix.")
            return

        active_layer = self.layer_cb.currentLayer() if self.tab_widget.currentIndex() == 0 else self.main_layer_cb.currentLayer()
        if not active_layer:
            return

        supported_types = {
            'Invalid Geometry',
            'Duplicate Geometry',
            'Multipart Geometry',
            'Spike / Acute Vertex',
            'Overlap',
            'Micro Polygon / Sliver',
            'Prolonged Edge / Overshoot',
            'Missing Node / Line Intersection',
            'Cross-Layer Overlap',
            'Cross-Layer Missing Node / Line Intersection'
        }

        fixable_errors = [e for e in filtered if e.error_type in supported_types]
        if not fixable_errors:
            QMessageBox.warning(self, "No Fixable Errors", "None of the errors can be automatically fixed.")
            return

        reply = QMessageBox.question(
            self, "Confirm Bulk Auto-Fix All",
            f"Are you sure you want to automatically fix all {len(fixable_errors)} fixable error(s)?\nThis will modify the vector layer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_autofix.setEnabled(False)

        fixed_count = 0
        failed_count = 0
        all_affected_fids = []
        edited_layers = set()

        try:
            for err in fixable_errors:
                if err.error_type == 'Cross-Layer Overlap':
                    main_fid = err.feature_ids[0]
                    other_fid = err.feature_ids[1]
                    main_l = err.feature_layers[0] if len(err.feature_layers) > 0 else None
                    other_l = err.feature_layers[1] if len(err.feature_layers) > 1 else None
                    if main_l and other_l:
                        if not main_l.getFeature(main_fid).isValid():
                            fixed_count += 1
                            continue

                        main_l.startEditing()
                        edited_layers.add(main_l)
                        if TopologyFixer.fix_cross_layer_overlap(main_l, main_fid, other_l, other_fid):
                            fixed_count += 1
                            all_affected_fids.append(main_fid)
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1

                elif err.error_type == 'Cross-Layer Missing Node / Line Intersection':
                    main_fid = err.feature_ids[0]
                    main_l = err.feature_layers[0] if len(err.feature_layers) > 0 else None
                    if main_l and main_l.getFeature(main_fid).isValid():
                        main_l.startEditing()
                        edited_layers.add(main_l)
                        if TopologyFixer.fix_missing_node(main_l, main_fid, err.location_x, err.location_y):
                            fixed_count += 1
                            all_affected_fids.append(main_fid)
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1
                else:
                    features_exist = True
                    for fid in err.feature_ids:
                        f = active_layer.getFeature(fid)
                        if not f.isValid():
                            features_exist = False
                            break
                    if not features_exist:
                        fixed_count += 1
                        continue

                    active_layer.startEditing()
                    edited_layers.add(active_layer)
                    if err.error_type == 'Invalid Geometry':
                        if TopologyFixer.fix_invalid_geometry(active_layer, err.feature_ids[0]):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Duplicate Geometry':
                        if TopologyFixer.fix_duplicate_geometry(active_layer, err.feature_ids[0]):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Multipart Geometry':
                        if TopologyFixer.fix_multipart_geometry(active_layer, err.feature_ids[0]):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Spike / Acute Vertex':
                        if TopologyFixer.fix_spike_geometry(active_layer, err.feature_ids[0], err.location_x, err.location_y):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Overlap':
                        if len(err.feature_ids) >= 2:
                            if TopologyFixer.fix_overlap_geometry(active_layer, err.feature_ids[0], err.feature_ids[1]):
                                fixed_count += 1
                                all_affected_fids.extend(err.feature_ids)
                            else:
                                failed_count += 1
                        else:
                            failed_count += 1

                    elif err.error_type == 'Micro Polygon / Sliver':
                        if TopologyFixer.fix_sliver_geometry(active_layer, err.feature_ids[0]):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Prolonged Edge / Overshoot':
                        if TopologyFixer.fix_overshoot_geometry(active_layer, err.feature_ids[0]):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

                    elif err.error_type == 'Missing Node / Line Intersection':
                        target_fid = err.feature_ids[0]
                        if TopologyFixer.fix_missing_node(active_layer, target_fid, err.location_x, err.location_y):
                            fixed_count += 1
                            all_affected_fids.extend(err.feature_ids)
                        else:
                            failed_count += 1

            if fixed_count > 0:
                msg = f"Auto-fixed {fixed_count} error(s) in edit buffer."
                if failed_count > 0:
                    msg += f" (Failed to fix {failed_count} error(s))."
                msg += "\n\nNote: The fixes have been applied in edit mode. Please review them and save or discard layer changes manually in QGIS."
                QMessageBox.information(self, "Success", msg)
                self.recheck_after_autofix(active_layer, list(set(all_affected_fids)))
            else:
                for l in edited_layers:
                    l.rollBack()
                QMessageBox.warning(self, "Error", "Failed to fix the error(s) automatically.")
        except Exception as e:
            for l in edited_layers:
                l.rollBack()
            QMessageBox.critical(self, "Error", f"An error occurred during auto-fix: {str(e)}")
        finally:
            has_errs = len(self.errors) > 0
            self.btn_autofix.setEnabled(has_errs)

    def recheck_after_autofix(self, layer, fids):
        self.run_recheck_async(layer, fids)

    def user_create_error_layer(self):
        layer = self.layer_cb.currentLayer() if self.tab_widget.currentIndex() == 0 else self.main_layer_cb.currentLayer()
        if not layer or not self.errors:
            QMessageBox.information(self, "Info", "No errors to export to a temporary layer.")
            return
        self.create_error_memory_layer(layer)
        QMessageBox.information(self, "Layer Created", "Temporary memory layer 'Topology Error Markers' added to QGIS layer panel.")

    def get_filtered_errors(self):
        selected_type = self.filter_cb.currentText()
        query = self.search_edit.text().strip().lower() if hasattr(self, 'search_edit') else ""

        res = self.errors
        if selected_type and selected_type != "All Error Types":
            if selected_type == "Gap / Void":
                res = [e for e in res if e.error_type in ("Gap / Sliver Void", "Enclosed Gap / Void")]
            elif selected_type == "Missing Node / Line Intersection":
                res = [e for e in res if e.error_type in ("Missing Node / Line Intersection", "Cross-Layer Missing Node / Line Intersection")]
            else:
                res = [e for e in res if e.error_type == selected_type]

        if query:
            res = [
                e for e in res
                if query in e.error_type.lower() or query in e.description.lower() or any(query in str(fid) for fid in e.feature_ids)
            ]
        return res

    def populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        filtered = self.get_filtered_errors()
        for idx, err in enumerate(filtered):
            try:
                original_idx = self.errors.index(err)
            except ValueError:
                original_idx = -1
            self.table.insertRow(idx)
            item = QTableWidgetItem(str(idx + 1))
            item.setData(USER_ROLE, original_idx)
            self.table.setItem(idx, 0, item)
            self.table.setItem(idx, 1, QTableWidgetItem(", ".join(map(str, err.feature_ids))))
            self.table.setItem(idx, 2, QTableWidgetItem(err.error_type))
            self.table.setItem(idx, 3, QTableWidgetItem(err.description))
            self.table.setItem(idx, 4, QTableWidgetItem(f"{err.location_x:.4f}, {err.location_y:.4f}"))
        self.table.setSortingEnabled(True)

    def clear_all_canvas_markers(self):
        if not self.iface:
            return
        canvas = self.iface.mapCanvas()

        if hasattr(self, 'rubber_band') and self.rubber_band:
            try:
                self.rubber_band.reset()
                canvas.scene().removeItem(self.rubber_band)
            except Exception:  # nosec B110
                pass
            self.rubber_band = None

        if hasattr(self, 'vertex_marker') and self.vertex_marker:
            try:
                canvas.scene().removeItem(self.vertex_marker)
            except Exception:  # nosec B110
                pass
            self.vertex_marker = None

        for m in getattr(self, 'all_markers', []):
            try:
                canvas.scene().removeItem(m)
            except Exception:  # nosec B110
                pass
        self.all_markers = []

        for rb in getattr(self, 'all_rubber_bands', []):
            try:
                rb.reset()
                canvas.scene().removeItem(rb)
            except Exception:  # nosec B110
                pass
        self.all_rubber_bands = []

        for prb in getattr(self, 'parent_rubber_bands', []):
            try:
                prb.reset()
                canvas.scene().removeItem(prb)
            except Exception:  # nosec B110
                pass
        self.parent_rubber_bands = []

        for prb in getattr(self, 'preview_rubber_bands', []):
            try:
                prb.reset()
                canvas.scene().removeItem(prb)
            except Exception:  # nosec B110
                pass
        self.preview_rubber_bands = []

        self.highlights_active = False
        if hasattr(self, 'btn_toggle_highlight') and self.btn_toggle_highlight:
            self.btn_toggle_highlight.setText("Highlight Errors")
            self.btn_toggle_highlight.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 6px;")

        canvas.refresh()

    def closeEvent(self, event):
        self.clear_all_canvas_markers()
        super().closeEvent(event)

    def reject(self):
        self.clear_all_canvas_markers()
        super().reject()

    def highlight_all_errors(self):
        if not self.iface:
            return
        if hasattr(self, 'cb_show_highlights') and not self.cb_show_highlights.isChecked():
            self.cb_show_highlights.setChecked(True)
        self.clear_all_canvas_markers()
        canvas = self.iface.mapCanvas()

        filtered = self.get_filtered_errors()
        if not filtered:
            QMessageBox.information(self, "Info", "No errors to display for the selected filter.")
            return

        combined_extent = None

        for err in filtered:
            # Create rubberband outline for geometry
            if err.geometry:
                is_poly = (err.geometry.type() == QgsWkbTypes.GeometryType.PolygonGeometry)
                rb = QgsRubberBand(canvas, is_poly)
                rb.setColor(QColor(255, 0, 0, 120))
                rb.setStrokeColor(QColor(255, 0, 0, 220))
                rb.setWidth(3)
                rb.setToGeometry(err.geometry, None)
                self.all_rubber_bands.append(rb)

            # Create vertex marker for point
            vm = QgsVertexMarker(canvas)
            vm.setCenter(QgsPointXY(err.location_x, err.location_y))
            vm.setColor(QColor(255, 0, 0))
            vm.setPenWidth(3)
            vm.setIconSize(14)
            vm.setIconType(QgsVertexMarker.IconType.ICON_X)
            self.all_markers.append(vm)

            # Update extent
            pt_rect = QgsRectangle(err.location_x - 1, err.location_y - 1, err.location_x + 1, err.location_y + 1)
            if combined_extent is None:
                combined_extent = pt_rect
            else:
                combined_extent.combineExtentWith(pt_rect)

        if combined_extent:
            combined_extent.scale(1.3)
            canvas.setExtent(combined_extent)
            canvas.refresh()

    def on_table_select(self):
        if not hasattr(self, 'cb_show_highlights') or not self.cb_show_highlights.isChecked():
            self.clear_all_canvas_markers()
            return
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.clear_all_canvas_markers()
            return
        row = selected_rows[0].row()
        item = self.table.item(row, 0)
        if not item:
            return
        original_idx = item.data(USER_ROLE)
        if original_idx is not None and 0 <= original_idx < len(self.errors):
            err = self.errors[original_idx]
            self.highlight_error(err)
            self.highlights_active = True
            if hasattr(self, 'btn_toggle_highlight') and self.btn_toggle_highlight:
                self.btn_toggle_highlight.setText("Clear Highlights")
                self.btn_toggle_highlight.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold; padding: 6px;")
            if err.error_type in ('Overlap', 'Cross-Layer Overlap') and hasattr(self, 'lbl_summary'):
                self.lbl_summary.setText(f"Selected: {err.error_type}. Proposed fix preview shown in dashed green on map.")

    def on_table_double_click(self, row, column):
        item = self.table.item(row, 0)
        if item:
            original_idx = item.data(USER_ROLE)
            if original_idx is not None and 0 <= original_idx < len(self.errors):
                err = self.errors[original_idx]
                self.zoom_to_error(err)

    def highlight_error(self, err):
        if not self.iface:
            return
        self.clear_all_canvas_markers()
        canvas = self.iface.mapCanvas()

        if err.feature_ids:
            self.parent_rubber_bands = []
            for idx, fid in enumerate(err.feature_ids):
                target_layer = None
                if hasattr(err, 'feature_layers') and idx < len(err.feature_layers):
                    target_layer = err.feature_layers[idx]
                if not target_layer:
                    target_layer = self.layer_cb.currentLayer() if self.tab_widget.currentIndex() == 0 else self.main_layer_cb.currentLayer()
                
                if target_layer:
                    feat = target_layer.getFeature(fid)
                    if feat.isValid() and feat.geometry() and not feat.geometry().isEmpty():
                        parent_rb = QgsRubberBand(canvas, True)
                        # Semi-transparent orange fill with red border to show the parent feature context clearly
                        parent_rb.setColor(QColor(255, 165, 0, 50))
                        parent_rb.setSecondaryStrokeColor(QColor(255, 140, 0, 180))
                        parent_rb.setWidth(2)
                        parent_rb.setToGeometry(feat.geometry(), None)
                        self.parent_rubber_bands.append(parent_rb)

        is_poly = False
        if err.geometry:
            is_poly = (err.geometry.type() == QgsWkbTypes.GeometryType.PolygonGeometry)

        self.rubber_band = QgsRubberBand(canvas, is_poly)
        self.rubber_band.setColor(QColor(255, 0, 0, 150))
        self.rubber_band.setStrokeColor(QColor(255, 0, 0, 255))
        self.rubber_band.setWidth(4)

        if err.geometry:
            self.rubber_band.setToGeometry(err.geometry, None)

        self.vertex_marker = QgsVertexMarker(canvas)
        self.vertex_marker.setCenter(QgsPointXY(err.location_x, err.location_y))
        self.vertex_marker.setColor(QColor(255, 0, 0))
        self.vertex_marker.setPenWidth(3)
        self.vertex_marker.setIconSize(16)
        self.vertex_marker.setIconType(QgsVertexMarker.IconType.ICON_X)

        # Check if the error is automatically fixable and generate proposed geometry preview
        if err.error_type == 'Cross-Layer Overlap':
            main_fid = err.feature_ids[0]
            other_fid = err.feature_ids[1]
            main_l = err.feature_layers[0] if len(err.feature_layers) > 0 else None
            other_l = err.feature_layers[1] if len(err.feature_layers) > 1 else None
            if main_l and other_l:
                f_main = main_l.getFeature(main_fid)
                f_other = other_l.getFeature(other_fid)
                if f_main.isValid() and f_other.isValid():
                    new_geom = f_main.geometry().difference(f_other.geometry())
                    if new_geom and not new_geom.isEmpty():
                        preview_rb = QgsRubberBand(canvas, True)
                        preview_rb.setColor(QColor(46, 204, 113, 80)) # Semi-transparent green
                        preview_rb.setSecondaryStrokeColor(QColor(39, 174, 96, 220)) # Darker green border
                        preview_rb.setWidth(3)
                        preview_rb.setLineStyle(Qt.PenStyle.DashLine)
                        preview_rb.setToGeometry(new_geom, None)
                        self.preview_rubber_bands.append(preview_rb)
                        
        elif err.error_type == 'Overlap':
            layer = self.layer_cb.currentLayer()
            if layer and len(err.feature_ids) >= 2:
                feat1 = layer.getFeature(err.feature_ids[0])
                feat2 = layer.getFeature(err.feature_ids[1])
                if feat1.isValid() and feat2.isValid():
                    smaller_feat = feat1 if feat1.geometry().area() < feat2.geometry().area() else feat2
                    larger_feat = feat2 if smaller_feat.id() == feat1.id() else feat1
                    new_geom = smaller_feat.geometry().difference(larger_feat.geometry())
                    if new_geom and not new_geom.isEmpty():
                        preview_rb = QgsRubberBand(canvas, True)
                        preview_rb.setColor(QColor(46, 204, 113, 80))
                        preview_rb.setSecondaryStrokeColor(QColor(39, 174, 96, 220))
                        preview_rb.setWidth(3)
                        preview_rb.setLineStyle(Qt.PenStyle.DashLine)
                        preview_rb.setToGeometry(new_geom, None)
                        self.preview_rubber_bands.append(preview_rb)

        canvas.refresh()

    def zoom_to_error(self, err):
        if not self.iface:
            return
        canvas = self.iface.mapCanvas()

        if err.geometry and not err.geometry.isEmpty() and err.geometry.type() != 0:
            bbox = err.geometry.boundingBox()
            bbox.scale(1.5)
            canvas.setExtent(bbox)
        else:
            # Zoom directly to point
            rect = QgsRectangle(
                err.location_x - 5.0, err.location_y - 5.0,
                err.location_x + 5.0, err.location_y + 5.0
            )
            canvas.setExtent(rect)

        canvas.setCenter(QgsPointXY(err.location_x, err.location_y))
        canvas.refresh()
        self.highlight_error(err)

    def on_show_highlights_changed(self):
        if not self.cb_show_highlights.isChecked():
            self.clear_all_canvas_markers()
        else:
            self.on_table_select()

    def create_error_memory_layer(self, source_layer):
        if not self.errors:
            return
        mem_layer = QgsVectorLayer(f"Polygon?crs={source_layer.crs().authid()}", "Topology Error Markers", "memory")
        pr = mem_layer.dataProvider()
        pr.addAttributes([QgsField("Error_Type", QVariant.String), QgsField("FIDs", QVariant.String), QgsField("Details", QVariant.String)])
        mem_layer.updateFields()

        feats = []
        for err in self.errors:
            if err.geometry:
                f = QgsFeature()
                f.setGeometry(err.geometry)
                f.setAttributes([err.error_type, ", ".join(map(str, err.feature_ids)), err.description])
                feats.append(f)
        pr.addFeatures(feats)
        QgsProject.instance().addMapLayer(mem_layer)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Topology Error CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Row", "Feature_IDs", "Error_Type", "Description", "Location_X", "Location_Y"])
            for idx, err in enumerate(self.errors):
                writer.writerow([idx + 1, ", ".join(map(str, err.feature_ids)), err.error_type, err.description, err.location_x, err.location_y])
        QMessageBox.information(self, "Export Complete", f"CSV Error Report saved to:\n{path}")

    def export_html(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Topology Error HTML", "", "HTML Files (*.html)")
        if not path:
            return
        active_l = self.layer_cb.currentLayer() if self.tab_widget.currentIndex() == 0 else self.main_layer_cb.currentLayer()
        layer_name = active_l.name() if active_l else 'N/A'
        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>Topology Quality Report - {layer_name}</title>
<style>
body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 30px; background-color: #f4f6f9; }}
.header {{ background-color: #007acc; color: white; padding: 20px; border-radius: 6px; }}
h1 {{ margin: 0 0 10px 0; font-size: 24px; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 20px; background: white; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
th, td {{ border: 1px solid #e1e4e8; padding: 12px; text-align: left; }}
th {{ background-color: #f8f9fa; font-weight: bold; }}
tr:nth-child(even) {{ background-color: #f9fbfd; }}
.badge {{ background-color: #d9534f; color: white; padding: 3px 8px; border-radius: 10px; font-size: 12px; }}
</style>
</head>
<body>
<div class="header">
  <h1>Gruhanaksha Topology Quality Inspection Report</h1>
  <p><b>Target Vector Layer:</b> {layer_name}</p>
  <p><b>Total Errors Discovered:</b> <span class="badge">{len(self.errors)}</span></p>
</div>
<table>
<tr><th>#</th><th>Feature ID(s)</th><th>Error Type</th><th>Description</th><th>Location (X, Y)</th></tr>
"""
        for idx, err in enumerate(self.errors):
            html_content += f"<tr><td>{idx+1}</td><td>{', '.join(map(str, err.feature_ids))}</td><td><b>{err.error_type}</b></td><td>{err.description}</td><td>{err.location_x:.4f}, {err.location_y:.4f}</td></tr>\n"
        html_content += "</table></body></html>"

        with open(path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        QMessageBox.information(self, "Export Complete", f"HTML Error Report saved to:\n{path}")
