"""Consistency checks between declarative catalogues and the code that implements them."""

import importlib
import inspect
import pkgutil

import pytest

import watchstreet
from watchstreet.domain import WorkflowKey
from watchstreet.errors import WatchStreetError
from watchstreet.workflow_specs import SPECS, get_spec
from watchstreet.workflows.definitions import REGISTRY, get_workflow, user_workflows


def test_every_workflow_key_has_spec_and_implementation() -> None:
    assert set(SPECS) == set(WorkflowKey)
    assert set(REGISTRY) == set(SPECS)


def test_registry_order_matches_spec_order() -> None:
    assert list(REGISTRY) == list(SPECS)


def test_workflow_metadata_comes_from_the_spec() -> None:
    for key, workflow in REGISTRY.items():
        spec = SPECS[key]
        assert workflow.key == spec.key
        assert workflow.label == spec.label
        assert workflow.description == spec.description
        assert workflow.user_creatable == spec.user_creatable
        assert workflow.needs_topic == spec.needs_topic


def test_user_workflows_are_the_user_creatable_specs() -> None:
    assert [w.key for w in user_workflows()] == [k for k, s in SPECS.items() if s.user_creatable]


def test_unknown_workflow_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown workflow"):
        get_spec("nope")
    with pytest.raises(ValueError, match="Unknown workflow"):
        get_workflow("nope")


def test_default_title_includes_topic() -> None:
    spec = SPECS[WorkflowKey.TOPIC_ANALYSIS]
    assert spec.default_title("ABC", "Risiken") == "Themenanalyse – ABC: Risiken"
    assert spec.default_title("ABC", "") == "Themenanalyse – ABC"


def test_all_deliberate_errors_share_one_root() -> None:
    found = set()
    for info in pkgutil.walk_packages(watchstreet.__path__, "watchstreet."):
        if info.name.startswith("watchstreet.web") or info.name.endswith("worker"):
            continue
        module = importlib.import_module(info.name)
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__ and name.endswith("Error"):
                found.add(cls)
                assert issubclass(cls, WatchStreetError), name
    assert len(found) >= 8
