import json

from factory.config import ROOT


def test_notebook_is_valid_and_cells_are_python():
    # nbformat is a verification tool, intentionally absent from application dependencies.
    import nbformat
    notebook = nbformat.read(ROOT/'notebooks/content_factory_colab.ipynb', as_version=4)
    nbformat.validate(notebook)
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type == 'code':
            compile(cell.source, f'colab-cell-{index}', 'exec')
    source = json.dumps(notebook)
    assert 'RENDER_COMMIT_PLACEHOLDER' not in source
    for forbidden in ('factory.main', 'factory.config', 'OPENAI_API_KEY', 'uvicorn', 'ngrok', 'while True'):
        assert forbidden not in source
    assert '975c58fcb244273838534bba771e64ad87739216b0f9b39a888531a49a72d845' in source
    assert 'drive.mount' in source and 'MOUNT_DRIVE = False' in source
