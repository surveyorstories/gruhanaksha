from PyQt5 import QtWidgets, QtCore
from qgis.core import QgsExpressionContextUtils, QgsProject


class MasterWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Master Panel')

        # District list
        self.district_names = {
            'Alluri Sitharama Raju': 'అల్లూరి సీతారామ రాజు', 'Anakapalli': 'అనకాపల్లి', 'Anantapuram': 'అనంతపురం',
            'Annamayya': 'అన్నమయ్య', 'Bapatla': 'బాపట్ల', 'Chittoor': 'చిత్తూరు', 'East Godavari': 'తూర్పు గోదావరి',
            'Eluru': 'ఏలూరు', 'Guntur': 'గుంటూరు', 'Kakinada': 'కాకినాడ', 'Dr. B. R. Ambedkar Konaseema': 'కోనసీమ',
            'Krishna': 'కృష్ణా', 'Kurnool': 'కర్నూలు', 'Nandyal': 'నంద్యాల', 'NTR': 'యన్.టి.ఆర్', 'Palnadu': 'పల్నాడు',
            'Parvathipuram Manyam': 'పార్వతీపురం మన్యం', 'Prakasam': 'ప్రకాశం', 'Sri Potti Sriramulu Nellore': 'నెల్లూరు',
            'Sri Sathya Sai': 'శ్రీ సత్య సాయి', 'Srikakulam': 'శ్రీకాకుళం', 'Tirupati': 'తిరుపతి',
            'Visakhapatnam': 'విశాఖపట్నం', 'Vizianagaram': 'విజయనగరం', 'West Godavari': 'పశ్చిమ గోదావరి',
            'YSR Kadapa': 'వై.యస్.ర్ కడప'
        }

        # Widgets
        self.district_name = QtWidgets.QComboBox()
        self.mandal_name_eng = QtWidgets.QLineEdit()
        self.panchayat_name = QtWidgets.QLineEdit()
        self.grama_panchayat_code = QtWidgets.QLineEdit()
        self.village_code = QtWidgets.QLineEdit()

        self.populate_district_combobox()

        # Dictionary of widgets
        self.widgets = {
            'Mandal_Name_eng': self.mandal_name_eng,
            'Panchyat_eng': self.panchayat_name,
            'Panchyat_Code': self.grama_panchayat_code,
            'P_LGD_Code': self.village_code,
        }

        self.global_keys = list(self.widgets.keys())

        # Layout
        form_layout = QtWidgets.QFormLayout()
        form_layout.addRow("Choose Your District:", self.district_name)
        form_layout.addRow("Mandal Name (English):", self.mandal_name_eng)
        form_layout.addRow("Panchayat Name:", self.panchayat_name)
        form_layout.addRow("Grama Panchayat Code:", self.grama_panchayat_code)
        form_layout.addRow("Village (LGD)Code:", self.village_code)

        self.clear_button = QtWidgets.QPushButton("Clear")
        self.update_button = QtWidgets.QPushButton("Update")
        self.clear_button.setStyleSheet("background-color: black; color: white;")
        self.update_button.setStyleSheet("background-color: black; color: white;")
        self.clear_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.update_button.setCursor(QtCore.Qt.PointingHandCursor)

        self.clear_button.clicked.connect(self.clear_data)
        self.update_button.clicked.connect(self.update_data)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.update_button)

        form_layout.addRow(button_layout)

        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(form_layout)
        self.setLayout(main_layout)

    def showEvent(self, event):
        super().showEvent(event)
        self.set_default_values_from_project()

    def populate_district_combobox(self):
        for district, telugu in self.district_names.items():
            self.district_name.addItem(f"{district} ({telugu})", district)

    def set_default_values_from_project(self):
        self.clear_data()

        # Load from global variables
        district_name_default = QgsExpressionContextUtils.globalScope().variable('district_eng')
        if district_name_default is not None:
            for i in range(self.district_name.count()):
                if self.district_name.itemData(i) == district_name_default:
                    self.district_name.setCurrentIndex(i)
                    break

        for var in self.global_keys:
            if QgsExpressionContextUtils.globalScope().hasVariable(var):
                value = QgsExpressionContextUtils.globalScope().variable(var)
                if isinstance(self.widgets[var], QtWidgets.QLineEdit):
                    self.widgets[var].setText(str(value))

        # Load from project variables (optional)
        for key, widget in self.widgets.items():
            proj_val = QgsExpressionContextUtils.projectScope(QgsProject.instance()).variable(key)
            if proj_val:
                widget.setText(str(proj_val))

    def update_data(self):
        # Save district name (eng and telugu)
        district_eng = self.district_name.currentData()
        district_tel = self.district_names[district_eng]
        QgsExpressionContextUtils.setGlobalVariable('district_eng', district_eng)
        QgsExpressionContextUtils.setGlobalVariable('District_Name', district_tel)

        # Save inputs to global and project variables in Proper Case
        for key, widget in self.widgets.items():
            if isinstance(widget, QtWidgets.QLineEdit):
                val = widget.text().title()
                QgsExpressionContextUtils.setGlobalVariable(key, val)
                QgsExpressionContextUtils.setProjectVariable(QgsProject.instance(), key, val)

        QtWidgets.QMessageBox.information(self, "Data Updated", "Data has been successfully updated.")

    def clear_data(self):
        for widget in self.widgets.values():
            if isinstance(widget, QtWidgets.QLineEdit):
                widget.clear()
        self.district_name.setCurrentIndex(0)



# Show the widget
master = MasterWidget()

