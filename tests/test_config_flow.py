from selectors import SelectSelector
from typing import Any

import pytest
import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.components import sensor
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
    POWER_WATT,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.typing import ConfigType
from homeassistant.setup import async_setup_component

import custom_components.test.sensor as test_sensor_platform
from custom_components.powercalc.config_flow import (
    CONF_CONFIRM_AUTODISCOVERED_MODEL,
    DOMAIN,
    ConfigFlow,
)
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_DAILY_FIXED_ENERGY,
    CONF_FIXED,
    CONF_GROUP_POWER_ENTITIES,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_POWER_FACTOR,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STATES_POWER,
    CONF_UPDATE_FREQUENCY,
    CONF_VALUE,
    CONF_VOLTAGE,
    CONF_WLED,
    CalculationStrategy,
    SensorType,
)
from custom_components.test.light import MockLight

from .common import MockConfigEntry, create_mock_light_entity

DEFAULT_ENTITY_ID = "light.test"
DEFAULT_UNIQUE_ID = "7c009ef6829f"


async def test_sensor_type_menu_displayed(hass: HomeAssistant):
    """Test a menu is diplayed with sensor type selection"""

    result: FlowResult = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == "user"


@pytest.mark.parametrize(
    "sensor_type",
    [SensorType.VIRTUAL_POWER, SensorType.DAILY_ENERGY, SensorType.GROUP],
)
async def test_sensor_type_form_displayed(hass: HomeAssistant, sensor_type: SensorType):
    await _select_sensor_type(hass, sensor_type)


async def test_create_fixed_sensor_entry(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_POWER: 20}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED, result["data"], {CONF_FIXED: {CONF_POWER: 20}}
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_fixed_sensor_entry_with_template(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)

    template = "{states(input_number.my_number} | float"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_POWER_TEMPLATE: template}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {CONF_FIXED: {CONF_POWER: template, CONF_POWER_TEMPLATE: template}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_fixed_sensor_entry_with_states_power(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STATES_POWER: ""}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED, result["data"], {CONF_FIXED: {CONF_STATES_POWER: ""}}
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_linear_sensor_entry(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LINEAR)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MIN_POWER: 1, CONF_MAX_POWER: 40}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.LINEAR,
        result["data"],
        {CONF_LINEAR: {CONF_MIN_POWER: 1, CONF_MAX_POWER: 40}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_linear_sensor_error_mandatory_fields(hass: HomeAssistant):
    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LINEAR)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MIN_POWER: 20}
    )

    assert result["errors"]
    assert result["errors"]["base"] == "linear_mandatory"
    assert result["type"] == data_entry_flow.FlowResultType.FORM


async def test_create_wled_sensor_entry(hass: HomeAssistant):
    await _create_wled_entities(hass)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.WLED)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VOLTAGE: 12, CONF_POWER_FACTOR: 0.8}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.WLED,
        result["data"],
        {CONF_WLED: {CONF_VOLTAGE: 12, CONF_POWER_FACTOR: 0.8}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_lut_manual_flow(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    await create_mock_light_entity(hass, light_entity)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_manufacturer"
    data_schema: vol.Schema = result["data_schema"]
    manufacturer_select: SelectSelector = data_schema.schema["manufacturer"]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "belkin", "label": "belkin"} in manufacturer_options
    assert {"value": "signify", "label": "signify"} in manufacturer_options

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MANUFACTURER: "signify"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_model"
    data_schema: vol.Schema = result["data_schema"]
    model_select: SelectSelector = data_schema.schema["model"]
    model_options = model_select.config["options"]
    assert {"value": "LCT010", "label": "LCT010"} in model_options
    assert {"value": "LWB010", "label": "LWB010"} in model_options

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODEL: "LCT010"}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.LUT,
        result["data"],
        {CONF_MANUFACTURER: "signify", CONF_MODEL: "LCT010"},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_lut_autodiscover_flow(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    light_entity.manufacturer = "ikea"
    light_entity.model = "LED1545G12"
    await create_mock_light_entity(hass, light_entity)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONFIRM_AUTODISCOVERED_MODEL: True}
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    _assert_default_virtual_power_entry_data(
        CalculationStrategy.LUT, result["data"], {}
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_lut_autodiscover_flow_not_confirmed(hass: HomeAssistant):
    """
    When manufacturer and model are auto detected and user chooses to not accept it,
    make sure he/she is forwarded to the manufacturer listing
    """
    light_entity = MockLight("test", STATE_ON, "234438")
    light_entity.manufacturer = "ikea"
    light_entity.model = "LED1545G12"
    await create_mock_light_entity(hass, light_entity)

    result = await _goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONFIRM_AUTODISCOVERED_MODEL: False}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "lut_manufacturer"


async def test_daily_energy_mandatory_fields_not_supplied(hass: HomeAssistant):
    result = await _select_sensor_type(hass, SensorType.DAILY_ENERGY)

    user_input = {CONF_NAME: "My daily energy sensor"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]
    assert result["errors"] == {"base": "daily_energy_mandatory"}


async def test_create_daily_energy_entry(hass: HomeAssistant):
    result = await _select_sensor_type(hass, SensorType.DAILY_ENERGY)

    user_input = {
        CONF_NAME: "My daily energy sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_VALUE: 20,
        CONF_UNIT_OF_MEASUREMENT: POWER_WATT,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
        CONF_NAME: "My daily energy sensor",
        CONF_DAILY_FIXED_ENERGY: {
            CONF_UPDATE_FREQUENCY: 1800,
            CONF_VALUE: 20,
            CONF_UNIT_OF_MEASUREMENT: POWER_WATT,
        },
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_daily_energy_sensor_energy")


async def test_create_group_entry(hass: HomeAssistant):
    result = await _select_sensor_type(hass, SensorType.GROUP)
    user_input = {
        CONF_NAME: "My group sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power", "sensor.bedroom1_power"],
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "My group sensor",
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power", "sensor.bedroom1_power"],
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_CREATE_UTILITY_METERS: False,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_group_sensor_power")


async def test_fixed_options_flow(hass: HomeAssistant):
    entry = _create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 40},
        },
    )

    result = await _initialize_options_flow(hass, entry)

    user_input = {CONF_POWER: 50}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_FIXED][CONF_POWER] == 50


async def test_wled_options_flow(hass: HomeAssistant):
    await _create_wled_entities(hass)

    entry = _create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.WLED,
            CONF_WLED: {CONF_VOLTAGE: 5},
        },
    )

    result = await _initialize_options_flow(hass, entry)

    user_input = {CONF_VOLTAGE: 12}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_WLED][CONF_VOLTAGE] == 12


async def test_linear_options_flow(hass: HomeAssistant):
    entry = _create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.LINEAR,
            CONF_LINEAR: {CONF_MIN_POWER: 10, CONF_MAX_POWER: 40},
        },
    )

    result = await _initialize_options_flow(hass, entry)

    user_input = {CONF_MAX_POWER: 50}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_LINEAR][CONF_MAX_POWER] == 50


async def test_daily_energy_options_flow(hass: HomeAssistant):
    entry = _create_mock_entry(
        hass,
        {
            CONF_NAME: "My daily energy sensor",
            CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
            CONF_DAILY_FIXED_ENERGY: {CONF_VALUE: 50},
        },
    )

    result = await _initialize_options_flow(hass, entry)

    user_input = {CONF_VALUE: 75, CONF_UNIT_OF_MEASUREMENT: POWER_WATT}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_DAILY_FIXED_ENERGY][CONF_UNIT_OF_MEASUREMENT] == POWER_WATT
    assert entry.data[CONF_DAILY_FIXED_ENERGY][CONF_VALUE] == 75


def _create_mock_entry(hass: HomeAssistant, entry_data: ConfigType) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data)
    entry.add_to_hass(hass)

    assert not entry.options
    return entry


async def _initialize_options_flow(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> FlowResult:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"
    return result


def _assert_default_virtual_power_entry_data(
    strategy: CalculationStrategy,
    config_entry_data: dict,
    expected_strategy_options=dict[str, Any],
):
    assert (
        config_entry_data
        == {
            CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: strategy,
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_NAME: "test",
            CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        }
        | expected_strategy_options
    )


async def _goto_virtual_power_strategy_step(
    hass: HomeAssistant,
    strategy: CalculationStrategy,
    user_input: dict[str, Any] | None = None,
) -> FlowResult:
    """
    - Select the virtual power sensor type
    - Select the given calculation strategy and put in default configuration options
    """

    if user_input is None:
        user_input = {
            CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
            CONF_MODE: strategy,
            CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        }

    result = await _select_sensor_type(hass, "virtual_power")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )

    # Lut has alternate flows depending on auto discovery, don't need to assert here
    if strategy != CalculationStrategy.LUT:
        assert result["step_id"] == strategy
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    return result


async def _select_sensor_type(
    hass: HomeAssistant, sensor_type: SensorType
) -> FlowResult:
    """Select a sensor type from the menu"""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": sensor_type}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == sensor_type

    return result


async def _create_wled_entities(hass: HomeAssistant):
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    await create_mock_light_entity(hass, light_entity)

    platform: test_sensor_platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    estimated_current_entity = platform.MockSensor(
        name="test_estimated_current", native_value="5.0", unique_id=DEFAULT_UNIQUE_ID
    )
    platform.ENTITIES[0] = estimated_current_entity

    assert await async_setup_component(
        hass, sensor.DOMAIN, {sensor.DOMAIN: {CONF_PLATFORM: "test"}}
    )
    await hass.async_block_till_done()
