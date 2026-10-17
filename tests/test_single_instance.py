import uuid
from PySide6.QtWidgets import QWidget
from macroflow.single_instance import SingleInstance, instance_name


def test_second_launch_restores_hidden_existing_window(qapp):
    name = 'Nexo-test-' + uuid.uuid4().hex
    owner = SingleInstance(name)
    second = SingleInstance(name)
    window = QWidget()
    try:
        assert owner.acquire()
        window.hide()
        owner.attach(window.showNormal)
        assert not second.acquire()
        for _ in range(5):
            qapp.processEvents()
        assert window.isVisible()
        assert owner.server.isListening()
    finally:
        window.close()
        owner.close()


def test_launch_during_startup_is_retained_and_lock_can_be_reused(qapp):
    name = 'Nexo-test-' + uuid.uuid4().hex
    owner = SingleInstance(name)
    second = SingleInstance(name)
    calls = []
    try:
        assert owner.acquire()
        assert not second.acquire()
        qapp.processEvents()
        owner.attach(lambda: calls.append('show'))
        for _ in range(5):
            qapp.processEvents()
        assert calls
        owner.close()
        assert second.acquire()
    finally:
        owner.close()
        second.close()


def test_normal_launch_scope_does_not_depend_on_data_folder(tmp_path):
    assert instance_name() == instance_name()
    assert instance_name(tmp_path / 'a') != instance_name(tmp_path / 'b')
    assert instance_name() != instance_name(tmp_path)


def test_simultaneous_processes_have_one_owner(tmp_path):
    import os
    import subprocess
    import sys
    script = tmp_path / 'launch.py'
    script.write_text("""
import sys
from PySide6.QtCore import QCoreApplication, QTimer
from macroflow.single_instance import SingleInstance
app = QCoreApplication([])
instance = SingleInstance(sys.argv[1])
if instance.acquire():
    print('owner', flush=True)
    QTimer.singleShot(2000, app.quit)
    app.exec()
    instance.close()
else:
    print('client', flush=True)
""", encoding='utf-8')
    env = dict(os.environ, PYTHONPATH=str(__import__('pathlib').Path(__file__).resolve().parents[1]))
    name = 'Nexo-test-' + uuid.uuid4().hex
    processes = [subprocess.Popen([sys.executable, str(script), name], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
    try:
        results = [process.communicate(timeout=15) for process in processes]
        assert all(process.returncode == 0 for process in processes), results
        assert [out.strip() for out, err in results].count('owner') == 1
        assert [out.strip() for out, err in results].count('client') == 3
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()


def test_exit_hidden_window_explicitly_quits_app(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from macroflow.config import Settings
    from macroflow.ui.main_window import MainWindow
    calls = []
    monkeypatch.setattr(QApplication, 'quit', lambda: calls.append('quit'))
    window = MainWindow(Settings(tmp_path), enable_hooks=False)
    window.hide()
    window.request_exit()
    assert window.closed and calls == ['quit']
