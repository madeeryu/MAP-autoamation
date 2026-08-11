"""
=====================================
DIALOG TAMBAH / EDIT PANGKALAN
=====================================
Form input data pangkalan: nama, nomor telepon (login MAP), password,
dan path file Excel NIK.

NOTE REKONSTRUKSI (2026): dialog dibangun ulang; field disesuaikan dengan
struktur config_manager (nama/telepon/password/excel_path).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QHBoxLayout, QLabel, QFileDialog, QMessageBox,
)


class DialogPangkalan(QDialog):
    def __init__(self, parent=None, pangkalan: dict | None = None):
        super().__init__(parent)
        self.pangkalan = pangkalan or {}
        self.setWindowTitle("Edit Pangkalan" if pangkalan else "Tambah Pangkalan")
        self.setMinimumWidth(420)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)

        judul = QLabel("Data Pangkalan")
        judul.setStyleSheet("font-size: 15px; font-weight: bold; margin-bottom: 6px;")
        root.addWidget(judul)

        form = QFormLayout()
        form.setSpacing(8)

        self.in_nama = QLineEdit(self.pangkalan.get("nama", ""))
        self.in_nama.setPlaceholderText("mis. Addenin")
        form.addRow("Nama:", self.in_nama)

        self.in_telepon = QLineEdit(self.pangkalan.get("telepon", ""))
        self.in_telepon.setPlaceholderText("Nomor HP login MAP, mis. 0812xxxx")
        form.addRow("Telepon:", self.in_telepon)

        self.in_password = QLineEdit(self.pangkalan.get("password", ""))
        self.in_password.setPlaceholderText("Password login MAP")
        self.in_password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password:", self.in_password)

        # Toggle lihat password
        self.btn_show_pw = QPushButton("👁")
        self.btn_show_pw.setFixedWidth(34)
        self.btn_show_pw.setCheckable(True)
        self.btn_show_pw.toggled.connect(self._toggle_pw)
        row_pw = QHBoxLayout()
        row_pw.addWidget(self.in_password)
        row_pw.addWidget(self.btn_show_pw)
        form.addRow("", row_pw)

        self.in_excel = QLineEdit(self.pangkalan.get("excel_path", "Data_NIK_Konsumen_LPG.xlsx"))
        btn_browse = QPushButton("Pilih...")
        btn_browse.clicked.connect(self._pilih_excel)
        row_excel = QHBoxLayout()
        row_excel.addWidget(self.in_excel)
        row_excel.addWidget(btn_browse)
        form.addRow("File Excel:", row_excel)

        root.addLayout(form)

        # Tombol aksi
        row_btn = QHBoxLayout()
        row_btn.addStretch()
        btn_batal = QPushButton("Batal")
        btn_batal.clicked.connect(self.reject)
        btn_simpan = QPushButton("Simpan")
        btn_simpan.setDefault(True)
        btn_simpan.clicked.connect(self._simpan)
        row_btn.addWidget(btn_batal)
        row_btn.addWidget(btn_simpan)
        root.addLayout(row_btn)

    def _toggle_pw(self, show: bool):
        self.in_password.setEchoMode(
            QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        )

    def _pilih_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih File Excel NIK", "", "Excel (*.xlsx *.xlsm)"
        )
        if path:
            self.in_excel.setText(path)

    def _simpan(self):
        if not self.in_nama.text().strip():
            QMessageBox.warning(self, "Validasi", "Nama pangkalan wajib diisi.")
            return
        if not self.in_telepon.text().strip():
            QMessageBox.warning(self, "Validasi", "Nomor telepon wajib diisi.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "nama":       self.in_nama.text().strip(),
            "telepon":    self.in_telepon.text().strip(),
            "password":   self.in_password.text(),
            "excel_path": self.in_excel.text().strip() or "Data_NIK_Konsumen_LPG.xlsx",
        }
