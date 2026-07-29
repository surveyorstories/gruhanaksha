# Qt6 Compatibility and Exceptions Refactoring Implementation Plan

This plan details the code changes required to fix Qt6 Enum compatibility warnings and refactor `try-except` blocks in `lpm_canvas.py`.

## User Review Required

> [!NOTE]
> All changes are fully backwards-compatible with PyQt5 / QGIS 3.34+ while ensuring compatibility with PyQt6 / QGIS 4+.
> Caught exceptions in `try-except` blocks will be logged to `QgsMessageLog` at the Warning level, which assists with troubleshooting without failing user workflows.

## Open Questions

None. The user has approved the design.

## Proposed Changes

### Gruhanaksha Plugin

#### [MODIFY] [lpm_canvas.py](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/lpm_canvas.py)

We will modify [lpm_canvas.py](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/lpm_canvas.py) in five locations:
1. Update imports to include `QgsMessageLog`.
2. Update the `QDialogButtonBox` enums to use `StandardButton` and `ButtonRole`.
3. Catch specific exceptions `(AttributeError, TypeError, ValueError)` in the vertices list generation loop and log.
4. Replace bare `except:` blocks on preview cleanup and log.
5. Update `QFont.Bold` to `QFont.Weight.Bold`.

---

### Task 1: Update Imports and Qt6 ButtonBox Enums

**Files:**
- Modify: [lpm_canvas.py](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/lpm_canvas.py#L11-L28)
- Modify: [lpm_canvas.py](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/lpm_canvas.py#L154-L159)

- [ ] **Step 1.1: Modify Imports**
  Add `QgsMessageLog` to the `qgis.core` import section in `lpm_canvas.py`.
  ```python
  from qgis.core import (
      QgsSymbol, QgsGeometry, QgsPointXY, QgsRuleBasedRenderer, QgsRectangle,
      QgsWkbTypes, QgsFeatureRequest, QgsSpatialIndex, QgsField,
      QgsSingleSymbolRenderer, QgsExpression, Qgis, QgsMapLayer, NULL,
      QgsAggregateCalculator, QgsApplication, QgsMapLayerStyle, QgsProject,
      QgsVectorLayer, QgsTextFormat, QgsTextBufferSettings, QgsPalLayerSettings,
      QgsVectorLayerSimpleLabeling, QgsFeature, QgsMessageLog
  )
  ```

- [ ] **Step 1.2: Update QDialogButtonBox enums on line 155-158**
  Change QDialogButtonBox shortcuts to explicit namespaces:
  ```python
          button_box = QDialogButtonBox()
          self.ok_button = button_box.addButton(QDialogButtonBox.StandardButton.Ok)
          self.cancel_button = button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
          self.preview_button = QPushButton("Preview")
          button_box.addButton(self.preview_button, QDialogButtonBox.ButtonRole.ActionRole)
  ```

- [ ] **Step 1.3: Run init tests to verify imports**
  Run:
  ```powershell
  $OSGEO4W_ROOT = "C:/Program Files/QGIS 3.34.13"; $env:PATH = "$OSGEO4W_ROOT/apps/qgis-ltr/bin;$OSGEO4W_ROOT/bin;$env:PATH"; $env:QGIS_PREFIX_PATH = "$OSGEO4W_ROOT/apps/qgis-ltr"; $env:QT_PLUGIN_PATH = "$OSGEO4W_ROOT/apps/qgis-ltr/qtplugins;$OSGEO4W_ROOT/apps/qt5/plugins"; $env:PYTHONPATH = "c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins;$OSGEO4W_ROOT/apps/qgis-ltr/python"; & "$OSGEO4W_ROOT/apps/Python312/python.exe" -m unittest gruhanaksha.test.test_init
  ```
  Expected: PASS

- [ ] **Step 1.4: Commit**
  ```bash
  git add lpm_canvas.py
  git commit -m "refactor: import QgsMessageLog and update QDialogButtonBox enums for Qt6"
  ```

---

### Task 2: Refactor Geometry Vertices Try-Except and QFont Bold

**Files:**
- Modify: [lpm_canvas.py](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/lpm_canvas.py#L1646-L1650)
- Modify: [lpm_canvas.py](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/lpm_canvas.py#L2239)

- [ ] **Step 2.1: Refactor vertices loop try-except block**
  Update `lpm_canvas.py` line 1646:
  ```python
              try:
                  vertices = list(geom.vertices())
              except (AttributeError, TypeError, ValueError) as e:
                  QgsMessageLog.logMessage(
                      f"Error getting geometry vertices: {e}",
                      "Gruhanaksha",
                      Qgis.MessageLevel.Warning
                  )
                  continue
  ```

- [ ] **Step 2.2: Update QFont.Bold to QFont.Weight.Bold**
  Update `lpm_canvas.py` line 2239:
  ```python
          text_format = QgsTextFormat()
          text_format.setFont(QFont("Verdana", 9, QFont.Weight.Bold))
          text_format.setColor(QColor("#1f78b4"))
  ```

- [ ] **Step 2.3: Commit**
  ```bash
  git add lpm_canvas.py
  git commit -m "refactor: update vertices try-except and standardize QFont.Weight.Bold"
  ```

---

### Task 3: Replace Bare Excepts on Preview Cleanup

**Files:**
- Modify: [lpm_canvas.py](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/lpm_canvas.py#L2145-L2155)

- [ ] **Step 3.1: Replace bare excepts in cleanup**
  Update line 2145:
  ```python
                  # Remove from project
                  QgsProject.instance().removeMapLayer(self.preview_layer.id())
              except Exception as e:
                  QgsMessageLog.logMessage(
                      f"Error removing preview layer: {e}",
                      "Gruhanaksha",
                      Qgis.MessageLevel.Warning
                  )
              self.preview_layer = None
          
          if hasattr(self, 'preview_rubber_band') and self.preview_rubber_band:
              try:
                  self.preview_rubber_band.reset()
              except Exception as e:
                  QgsMessageLog.logMessage(
                      f"Error resetting preview rubber band: {e}",
                      "Gruhanaksha",
                      Qgis.MessageLevel.Warning
                  )
              self.preview_rubber_band = None
  ```

- [ ] **Step 3.2: Verify with complete test suite run**
  Run:
  ```powershell
  $OSGEO4W_ROOT = "C:/Program Files/QGIS 3.34.13"; $env:PATH = "$OSGEO4W_ROOT/apps/qgis-ltr/bin;$OSGEO4W_ROOT/bin;$env:PATH"; $env:QGIS_PREFIX_PATH = "$OSGEO4W_ROOT/apps/qgis-ltr"; $env:QT_PLUGIN_PATH = "$OSGEO4W_ROOT/apps/qgis-ltr/qtplugins;$OSGEO4W_ROOT/apps/qt5/plugins"; $env:PYTHONPATH = "c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins;$OSGEO4W_ROOT/apps/qgis-ltr/python"; & "$OSGEO4W_ROOT/apps/Python312/python.exe" -m unittest discover -s c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/test -t c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins -p "test_*.py"
  ```
  Expected: Success for QGIS core/unit tests (except the pre-existing coordinate projection and translation failures).

- [ ] **Step 3.3: Commit**
  ```bash
  git add lpm_canvas.py
  git commit -m "refactor: replace bare excepts in canvas preview cleanup with explicit logging"
  ```

---

## Verification Plan

### Automated Tests
Run the unit test suite to verify code compiles, imports correctly, and executes without introducing regression.
```powershell
$OSGEO4W_ROOT = "C:/Program Files/QGIS 3.34.13"; $env:PATH = "$OSGEO4W_ROOT/apps/qgis-ltr/bin;$OSGEO4W_ROOT/bin;$env:PATH"; $env:QGIS_PREFIX_PATH = "$OSGEO4W_ROOT/apps/qgis-ltr"; $env:QT_PLUGIN_PATH = "$OSGEO4W_ROOT/apps/qgis-ltr/qtplugins;$OSGEO4W_ROOT/apps/qt5/plugins"; $env:PYTHONPATH = "c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins;$OSGEO4W_ROOT/apps/qgis-ltr/python"; & "$OSGEO4W_ROOT/apps/Python312/python.exe" -m unittest discover -s c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/test -t c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins -p "test_*.py"
```
