from Source.enter_point import Window
from PyQt6.QtWidgets import QApplication
import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    # todo: if first, auto open dialog for new race

    sys.exit(app.exec())
