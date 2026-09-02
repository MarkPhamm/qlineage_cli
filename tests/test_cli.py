import pytest

from qlineage import __version__
from qlineage.cli import main


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"qlineage {__version__}"


def test_ui_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["ui", "--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"qlineage {__version__}"
