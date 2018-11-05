import datetime
import json

import marshmallow
import pendulum
import pytest

import prefect
from prefect.engine import state
from prefect.serialization.state import StateSchema

all_states = set(
    cls
    for cls in state.__dict__.values()
    if isinstance(cls, type) and issubclass(cls, state.State) and cls is not state.State
)


def complex_states():
    naive_dt = datetime.datetime(2020, 1, 1)
    utc_dt = pendulum.datetime(2020, 1, 1)
    complex_result = {"x": 1, "y": {"z": 2}}
    cached_state = state.CachedState(
        cached_inputs=complex_result,
        cached_result=complex_result,
        cached_parameters=complex_result,
        cached_result_expiration=utc_dt,
    )
    cached_state_naive = state.CachedState(
        cached_inputs=complex_result,
        cached_result=complex_result,
        cached_parameters=complex_result,
        cached_result_expiration=naive_dt,
    )
    test_states = [
        state.Pending(cached_inputs=complex_result),
        state.Paused(cached_inputs=complex_result),
        state.Retrying(start_time=utc_dt, run_count=3),
        state.Retrying(start_time=naive_dt, run_count=3),
        state.Scheduled(start_time=utc_dt),
        state.Scheduled(start_time=naive_dt),
        cached_state,
        cached_state_naive,
        state.Success(result=complex_result, cached=cached_state),
        state.Success(result=complex_result, cached=cached_state_naive),
        state.TimedOut(cached_inputs=complex_result),
    ]
    return test_states


def test_all_states_have_serialization_schemas_in_stateschema():
    """
    Tests that all State subclasses in prefect.engine.states have corresponding schemas
    in prefect.serialization.state
    """
    assert set(s.__name__ for s in all_states) == set(StateSchema.type_schemas.keys())


def test_all_states_have_deserialization_schemas_in_stateschema():
    """
    Tests that all State subclasses in prefect.engine.states have corresponding schemas
    in prefect.serialization.state with that state assigned as the object class
    so it will be recreated at deserialization
    """
    assert all_states == set(
        s.Meta.object_class for s in StateSchema.type_schemas.values()
    )


@pytest.mark.parametrize("cls", all_states)
def test_serialize_state(cls):
    serialized = StateSchema().dump(cls(message="message", result=1))
    assert isinstance(serialized, dict)
    assert serialized["type"] == cls.__name__
    assert serialized["message"] is "message"
    assert serialized["result"] == "1"
    assert serialized["__version__"] == prefect.__version__


@pytest.mark.parametrize("cls", all_states)
def test_deserialize_state(cls):
    s = cls(message="message", result=1)
    serialized = StateSchema().dump(s)
    deserialized = StateSchema().load(serialized)
    assert isinstance(deserialized, cls)
    assert deserialized == s


@pytest.mark.parametrize("cls", all_states)
def test_deserialize_state_from_only_type(cls):
    serialized = dict(type=cls.__name__)
    new_state = StateSchema().load(serialized)
    assert isinstance(new_state, cls)
    assert new_state.message is None
    assert new_state.result is None


def test_deserialize_state_without_type_fails():
    with pytest.raises(marshmallow.exceptions.ValidationError):
        StateSchema().load({})


def test_deserialize_state_with_unknown_type_fails():
    with pytest.raises(marshmallow.exceptions.ValidationError):
        StateSchema().load({"type": "FakeState"})


@pytest.mark.parametrize("state", complex_states())
def test_complex_state_attributes_are_handled(state):
    serialized = StateSchema().dump(state)
    deserialized = StateSchema().load(serialized)
    assert state == deserialized


def test_result_is_serialized_as_json_string():
    s = state.Success(result={"x": 1})
    serialized = StateSchema().dump(s)
    assert serialized["result"] == json.dumps({"x": 1})


def test_result_deserializes_json_string():
    s = StateSchema().load({"type": "Success", "result": json.dumps({"x": {"y": 2}})})
    assert s.result == {"x": {"y": 2}}


def test_result_has_max_size_respected_during_serialization():
    payload = "x" * 20000  # over 16kb
    s = state.Success(result=payload)
    with pytest.raises(ValueError) as exc:
        StateSchema().dump(s)
    assert "payload exceeds max size" in str(exc).lower()


def test_result_has_max_size_respected_during_deserialization():
    payload = "x" * 20000  # over 16kb
    state.Success(result=payload)
    with pytest.raises(ValueError) as exc:
        StateSchema().load({"type": "Success", "result": json.dumps(payload)})
    assert "payload exceeds max size" in str(exc).lower()
