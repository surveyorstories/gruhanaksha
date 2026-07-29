# Design: Qt6 Compatibility & Try/Except Refactoring in lpm_canvas.py

- Date: 2026-07-29
- Goal: Fix Qt6 Enum compatibility issues and refactor bare excepts / silent continue exceptions.

## Proposed Changes

### [lpm_canvas.py](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/lpm_canvas.py)

#### 1. Import `QgsMessageLog`
Add `QgsMessageLog` to `qgis.core` import:
```diff
 from qgis.core import (
     QgsSymbol, QgsGeometry, QgsPointXY, QgsRuleBasedRenderer, QgsRectangle,
     QgsWkbTypes, QgsFeatureRequest, QgsSpatialIndex, QgsField,
     QgsSingleSymbolRenderer, QgsExpression, Qgis, QgsMapLayer, NULL,
     QgsAggregateCalculator, QgsApplication, QgsMapLayerStyle, QgsProject,
-    QgsVectorLayer, QgsTextFormat, QgsTextBufferSettings, QgsPalLayerSettings,
-    QgsVectorLayerSimpleLabeling, QgsFeature
+    QgsVectorLayer, QgsTextFormat, QgsTextBufferSettings, QgsPalLayerSettings,
+    QgsVectorLayerSimpleLabeling, QgsFeature, QgsMessageLog
 )
```

#### 2. Standardize `QDialogButtonBox` Enums
Specify explicit namespaces `StandardButton` and `ButtonRole`:
```diff
         # Buttons
         button_box = QDialogButtonBox()
-        self.ok_button = button_box.addButton(QDialogButtonBox.Ok)
-        self.cancel_button = button_box.addButton(QDialogButtonBox.Cancel)
+        self.ok_button = button_box.addButton(QDialogButtonBox.StandardButton.Ok)
+        self.cancel_button = button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
         self.preview_button = QPushButton("Preview")
-        button_box.addButton(self.preview_button, QDialogButtonBox.ActionRole)
+        button_box.addButton(self.preview_button, QDialogButtonBox.ButtonRole.ActionRole)
```

#### 3. Refactor Geometry Vertex Try-Except Block
Catch `(AttributeError, TypeError, ValueError)` instead of `Exception` and log via `QgsMessageLog`:
```diff
             try:
                 vertices = list(geom.vertices())
-            except Exception:
+            except (AttributeError, TypeError, ValueError) as e:
+                QgsMessageLog.logMessage(
+                    f"Error getting geometry vertices: {e}",
+                    "Gruhanaksha",
+                    Qgis.MessageLevel.Warning
+                )
                 continue
```

#### 4. Replace Bare Excepts in Canvas Preview Cleanup
Replace bare `except:` with `except Exception as e:` and log warning messages:
```diff
                 # Remove from project
                 QgsProject.instance().removeMapLayer(self.preview_layer.id())
-            except:
-                pass
+            except Exception as e:
+                QgsMessageLog.logMessage(
+                    f"Error removing preview layer: {e}",
+                    "Gruhanaksha",
+                    Qgis.MessageLevel.Warning
+                )
             self.preview_layer = None
         
         if hasattr(self, 'preview_rubber_band') and self.preview_rubber_band:
             try:
                 self.preview_rubber_band.reset()
-            except:
-                pass
+            except Exception as e:
+                QgsMessageLog.logMessage(
+                    f"Error resetting preview rubber band: {e}",
+                    "Gruhanaksha",
+                    Qgis.MessageLevel.Warning
+                )
             self.preview_rubber_band = None
```

#### 5. Standardize `QFont.Bold` to `QFont.Weight.Bold`
```diff
         text_format = QgsTextFormat()
-        text_format.setFont(QFont("Verdana", 9, QFont.Bold))
+        text_format.setFont(QFont("Verdana", 9, QFont.Weight.Bold))
         text_format.setColor(QColor("#1f78b4"))
```

## Verification Plan

### Automated Tests
- Run unit test suite:
  ```powershell
  $OSGEO4W_ROOT = "C:/Program Files/QGIS 3.34.13"; $env:PATH = "$OSGEO4W_ROOT/apps/qgis-ltr/bin;$OSGEO4W_ROOT/bin;$env:PATH"; $env:QGIS_PREFIX_PATH = "$OSGEO4W_ROOT/apps/qgis-ltr"; $env:QT_PLUGIN_PATH = "$OSGEO4W_ROOT/apps/qgis-ltr/qtplugins;$OSGEO4W_ROOT/apps/qt5/plugins"; $env:PYTHONPATH = "c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins;$OSGEO4W_ROOT/apps/qgis-ltr/python"; & "$OSGEO4W_ROOT/apps/Python312/python.exe" -m unittest discover -s c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/test -t c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins -p "test_*.py"
  ```
