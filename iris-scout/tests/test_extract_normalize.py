import pytest
from iris_scout.extract import extract_candidates
from iris_scout.models import Ecosystem as E, LLMResponse
from iris_scout.normalize import normalize


def ext(text):
    return extract_candidates(LLMResponse("p", "", "m", "t", text))


def names(cs):
    return [(c.ecosystem.value, c.raw_name) for c in cs]


def test_simple_pip_and_npm():
    assert names(ext("pip install requests\nnpm install lodash")) == [("pypi", "requests"), ("npm", "lodash")]

def test_pip_extras_and_pins_kept_as_spec():
    c = ext('pip install "requests[socks]>=2.31"')[0]
    assert (c.raw_name, c.spec) == ("requests", "[socks]>=2.31")

def test_multiple_packages_and_chained_commands():
    assert names(ext("pip install a b==1.0 && pip install c")) == [("pypi", "a"), ("pypi", "b"), ("pypi", "c")]

def test_flags_and_their_values_are_skipped():
    cs = ext("pip install -U --index-url https://x.y/simple --no-cache-dir foo")
    assert names(cs) == [("pypi", "foo")]

def test_requirements_file_is_flagged_not_a_package():
    cs = ext("pip install -r requirements.txt")
    assert cs == []   # -r consumes its value

def test_urls_paths_vcs_are_flagged():
    cs = ext("pip install git+https://github.com/psf/requests.git ./local.whl")
    assert all(c.note for c in cs) and len(cs) == 2

def test_python_dash_m_pip_and_uv():
    assert names(ext("python3 -m pip install a\nuv pip install b")) == [("pypi", "a"), ("pypi", "b")]

def test_npm_scoped_with_version_and_dev_flag():
    cs = ext("npm i -D @types/node@20 express@latest")
    assert [(c.raw_name, c.spec) for c in cs] == [("@types/node", "20"), ("express", "latest")]

def test_npm_github_shorthand_flagged():
    assert ext("npm install user/repo")[0].note

def test_inline_backticks_and_shell_prompt():
    assert names(ext("Run `pip install foo` now\n$ pip install bar")) == [("pypi", "foo"), ("pypi", "bar")]

def test_prose_without_commands_yields_nothing():
    assert ext("You should pip your install of ideas.") == []

def test_unbalanced_quotes_do_not_crash():
    assert ext('pip install "oops') == []

def test_environment_markers_dropped():
    c = ext("pip install 'foo>=1; python_version<\"3.9\"'")[0]
    assert c.raw_name == "foo"


@pytest.mark.parametrize("raw,expected", [
    ("Requests", "requests"), ("my_pkg.name", "my-pkg-name"), ("A--B", "a-b"),
])
def test_pypi_normalization_pep503(raw, expected):
    assert normalize(E.PYPI, raw) == expected

@pytest.mark.parametrize("raw", ["", "-bad", "bad-", "has space", "a/b"])
def test_pypi_invalid(raw):
    assert normalize(E.PYPI, raw) is None

def test_npm_scoped_valid_and_invalid():
    assert normalize(E.NPM, "@Types/Node") == "@types/node"
    assert normalize(E.NPM, "@/bad") is None
    assert normalize(E.NPM, "x" * 215) is None
