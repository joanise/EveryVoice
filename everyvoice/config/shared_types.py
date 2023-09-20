from collections.abc import Mapping, Sequence
from functools import cached_property
from pathlib import Path
from typing import Tuple, Union

from loguru import logger
from pydantic import BaseModel, ConfigDict, DirectoryPath, Field, validator

from everyvoice.config.utils import PossiblyRelativePath, PossiblySerializedCallable
from everyvoice.utils import generic_dict_loader, get_current_time, rel_path_to_abs_path


class ConfigModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
        json_schema_extra={"$schema": "http://json-schema.org/draft-07/schema#"},
    )

    def update_config(self, new_config: dict):
        """Update the config with new values"""
        new_data = self.combine_configs(dict(self), new_config)
        self.__init__(**new_data)  # type: ignore
        return self

    @staticmethod
    def combine_configs(orig_dict: Union[dict, Sequence], new_dict: dict):
        """See https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth"""
        if isinstance(orig_dict, Sequence):
            orig_list = list(orig_dict)
            for key_s, val in new_dict.items():
                key_i = int(key_s)
                if isinstance(val, Mapping):
                    tmp = ConfigModel.combine_configs(orig_list[key_i], val)  # type: ignore
                    orig_list[key_i] = tmp
                else:
                    orig_list[key_i] = val
            return orig_list

        orig_dict = dict(orig_dict)
        new_dict = dict(new_dict)
        for key, val in new_dict.items():
            if isinstance(val, Mapping):
                tmp = ConfigModel.combine_configs(orig_dict.get(key, {}), val)  # type: ignore
                orig_dict[key] = tmp
            else:
                orig_dict[key] = new_dict[key]
        return orig_dict


class LoggerConfig(ConfigModel):
    """The logger configures all the information needed for where to store your experiment's logs and checkpoints.
    The structure of your logs will then be:
    <name> / <version> / <sub_dir>
    <sub_dir> will be generated by calling <sub_dir_callable> each time the LoggerConfig is constructed.
    """

    name: str = "BaseExperiment"
    """The name of the experiment"""

    save_dir: DirectoryPath = Path("./logs_and_checkpoints")
    """The directory to save your checkpoints and logs to"""

    sub_dir_callable: PossiblySerializedCallable = get_current_time
    """The function that generates a string to call your runs - this should include a timestamp of some sort"""

    version: str = "base"
    """The version of your experiment"""

    @cached_property
    def sub_dir(self) -> str:
        return self.sub_dir_callable()

    # TODO[pydantic]: We couldn't refactor the `validator`, please replace it by `field_validator` manually.
    # Check https://docs.pydantic.dev/dev-v2/migration/#changes-to-validators for more information.
    @validator("save_dir", pre=True, always=True)
    def convert_path(cls, v, values):
        path = rel_path_to_abs_path(v)
        values["save_dir"] = path
        if not path.exists():
            logger.info(f"Directory at {path} does not exist. Creating...")
            path.mkdir(parents=True, exist_ok=True)
        return path


class BaseTrainingConfig(ConfigModel):
    batch_size: int = 16
    save_top_k_ckpts: int = 5
    ckpt_steps: Union[int, None] = None
    ckpt_epochs: Union[int, None] = 1
    max_epochs: int = 1000
    max_steps: int = 100000
    finetune_checkpoint: Union[PossiblyRelativePath, None] = None
    training_filelist: PossiblyRelativePath = Path(
        "./path/to/your/preprocessed/training_filelist.psv"
    )
    validation_filelist: PossiblyRelativePath = Path(
        "./path/to/your/preprocessed/validation_filelist.psv"
    )
    filelist_loader: PossiblySerializedCallable = generic_dict_loader
    logger: LoggerConfig = Field(default_factory=LoggerConfig)
    val_data_workers: int = 0
    train_data_workers: int = 4


class BaseOptimizer(ConfigModel):
    learning_rate: float = 1e-4
    eps: float = 1e-8
    weight_decay: float = 0.01


class RMSOptimizer(BaseOptimizer):
    alpha: float = 0.99
    name: str = "rms"


class AdamOptimizer(BaseOptimizer):
    betas: Tuple[float, float] = (0.9, 0.98)
    name: str = "adam"


class AdamWOptimizer(BaseOptimizer):
    betas: Tuple[float, float] = (0.9, 0.98)
    name: str = "adamw"


class NoamOptimizer(AdamOptimizer):
    warmup_steps: int = 4000
    name: str = "noam"
