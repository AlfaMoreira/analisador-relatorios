"""Glass Green adaptado à revisão documental desktop."""
from pathlib import Path
import sys

STYLE = """
QMainWindow { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0b1620,stop:1 #0a1a2b); }
QWidget { color:#dbe8f2; font-family:'Segoe UI'; font-size:13px; }
QLabel { background:transparent; }
QWidget#documentsPanel,QWidget#viewerPanel,QWidget#findingsPanel {
 background:rgba(20,35,51,225);border:1px solid rgba(181,222,235,28);border-radius:16px;
}
QPushButton { background:rgba(32,54,72,190);color:#dceaf1;border:1px solid #365469;border-radius:9px;padding:10px 13px; }
QPushButton:hover { background:#23485a;border:1px solid #2dd4bf;color:white; }
QPushButton:pressed { background:#103f42; }
QPushButton:disabled { color:#6f8797;background:#132333;border-color:#253b4c; }
QPushButton#primaryAction { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0d9488,stop:1 #0891a3);border:1px solid #2dd4bf;color:white;font-weight:600;padding:12px 22px; }
QPushButton#primaryAction:hover { background:#14a99c; }
QPushButton#addDocuments { background:#153b40;border:1px solid #267a75;color:#99f6e4;font-weight:600; }
QPushButton#connectAI { border-color:#278f86;color:#99f6e4;background:#133537; }
QLabel#aiStatus { border:1px solid #32645f;border-radius:13px;background:rgba(13,148,136,30);padding:7px 12px;color:#99f6e4; }
QLabel#brandLogo { background:#ffffff;border:1px solid #ffffff;border-radius:12px;padding:4px; }
QLabel#screenTitle { font-size:23px;font-weight:600;color:#f1f5f9; }
QLabel#subtitle,QLabel#footerStatus { color:#9fb7c9; }
QLabel#panelHeading { color:#7dd3c7;font-size:11px;font-weight:600;letter-spacing:1px;padding-bottom:6px; }
QLabel#reviewSummary { color:#c9f4eb;background:rgba(13,148,136,25);border:1px solid #255653;border-radius:10px;padding:12px; }
QListWidget,QTableWidget,QPlainTextEdit,QLineEdit,QComboBox,QSpinBox {
 background:#101f2e;color:#dceaf1;border:1px solid #2b4356;border-radius:8px;selection-background-color:#175f5b;selection-color:white;
}
QLineEdit { padding:9px; }
QComboBox { padding:8px; }
QComboBox QAbstractItemView { background:#152a3b;color:#dceaf1;selection-background-color:#166b62; }
QSpinBox {padding:7px;}
QPlainTextEdit {padding:9px;}
QListWidget {background:transparent;border:0;outline:0;}
QListWidget::item {border:1px solid #294254;border-radius:9px;padding:10px;margin-bottom:7px;background:#152a3a;}
QListWidget::item:selected {background:#164b4c;border-color:#28b4a1;color:#d8fff6;}
QTableWidget {gridline-color:#233d4d;border:0;alternate-background-color:#122839;}
QHeaderView::section {background:#172f40;color:#86b6bd;padding:9px;border:0;font-size:11px;font-weight:600;}
QTableWidget::item {padding:6px;}
QTableWidget::item:selected {background:#17554f;color:white;}
QScrollArea {background:#243644;border:1px solid #385060;border-radius:10px;}
QScrollBar:vertical {background:#112433;width:10px;border-radius:5px;}
QScrollBar::handle:vertical {background:#365469;border-radius:5px;min-height:30px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QCheckBox {spacing:8px;color:#b8dad9;}
QCheckBox::indicator {width:17px;height:17px;border:1px solid #477483;border-radius:4px;background:#102b39;}
QCheckBox::indicator:checked {background:#14b8a6;border-color:#5eead4;}
QProgressBar {background:#162f3e;border:0;border-radius:5px;max-height:7px;}
QProgressBar::chunk {background:#14b8a6;border-radius:5px;}
QSplitter::handle {background:transparent;width:12px;}
QToolTip {background:#173749;color:#e1fff7;border:1px solid #328b83;padding:6px;}
QMessageBox {background:#102637;}
"""

# Preferência do usuário: superfície clara, verde e azul da marca.
STYLE += """
QMainWindow { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #edf6f4,stop:1 #edf3fa); }
QWidget {color:#254458;}
QWidget#documentsPanel,QWidget#viewerPanel,QWidget#findingsPanel {background:rgba(255,255,255,240);border:1px solid #d7e5e9;}
QPushButton {background:#f6fafc;color:#24516a;border:1px solid #c5dce4;}
QPushButton:hover {background:#e7f5f2;color:#075f60;border-color:#55b6a8;}
QPushButton:pressed {background:#d8ede8;}
QPushButton:disabled {color:#93a5ad;background:#f0f5f6;border-color:#dde7ea;}
QPushButton#primaryAction {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #168f7f,stop:1 #1577ad);border:1px solid #278ba1;color:white;}
QPushButton#primaryAction:hover {background:#087d94;color:white;}
QPushButton#addDocuments {background:#e7f5ee;color:#176d56;border:1px solid #99cfbb;}
QPushButton#connectAI {background:#edf5fd;color:#145889;border-color:#9ec5df;}
QLabel#aiStatus {background:#e7f5f0;color:#18715e;border-color:#b6dbce;}
QLabel#screenTitle {color:#123c6d;}
QLabel#subtitle,QLabel#footerStatus {color:#607f91;}
QLabel#panelHeading {color:#217a72;}
QLabel#reviewSummary {background:#edf7f6;color:#1c6662;border-color:#c6e3dd;}
QListWidget,QTableWidget,QPlainTextEdit,QLineEdit,QComboBox,QSpinBox {background:white;color:#254458;border-color:#d0e0e7;selection-background-color:#d9eee9;selection-color:#124956;}
QComboBox QAbstractItemView {background:white;color:#254458;selection-background-color:#d9eee9;}
QListWidget {background:transparent;border:0;}
QListWidget::item {background:#f4f9fb;border-color:#dbe7ed;}
QListWidget::item:selected {background:#e1f1ec;color:#175c54;border-color:#70b7a5;}
QTableWidget {alternate-background-color:#f5fafb;gridline-color:#e5eef1;}
QHeaderView::section {background:#edf4f8;color:#4b7588;}
QTableWidget::item:selected {background:#dbeee9;color:#174d4e;}
QScrollArea {background:#dfeaf0;border-color:#c3d6e0;}
QScrollBar:vertical {background:#edf3f6;}
QScrollBar::handle:vertical {background:#b2cbd5;}
QCheckBox {color:#376a70;}
QCheckBox::indicator {background:white;border-color:#9bbdc8;}
QCheckBox::indicator:checked {background:#219b86;border-color:#168c7b;}
QProgressBar {background:#dce9ec;}
QToolTip {background:white;color:#234b60;border-color:#8fbdc8;}
QMessageBox,QDialog {background:#f5f9fb;}
"""


def logo_path():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "assets" / "celacanto-horizontal.jpeg"
