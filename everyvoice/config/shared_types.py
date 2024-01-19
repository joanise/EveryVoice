from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple, Union

from loguru import logger
from pydantic import (
    BaseModel,
    ConfigDict,
    DirectoryPath,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)
from typing_extensions import Annotated

from everyvoice.config.utils import PossiblyRelativePath, PossiblySerializedCallable
from everyvoice.utils import generic_dict_loader, get_current_time

_init_context_var = ContextVar("_init_context_var", default=None)


@contextmanager
def init_context(value: Dict[str, Any]) -> Iterator[None]:
    token = _init_context_var.set(value)  # type: ignore
    try:
        yield
    finally:
        _init_context_var.reset(token)


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
    def combine_configs(orig_dict: Union[dict, Sequence], new_dict: Mapping):
        """See https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth"""
        if isinstance(orig_dict, Sequence):
            orig_list = list(orig_dict)
            for key_s, val in new_dict.items():
                key_i = int(key_s)
                if isinstance(val, Mapping):
                    tmp = ConfigModel.combine_configs(orig_list[key_i], val)
                    orig_list[key_i] = tmp
                else:
                    orig_list[key_i] = val
            return orig_list

        orig_dict = dict(orig_dict)
        new_dict = dict(new_dict)
        for key, val in new_dict.items():
            if isinstance(val, Mapping):
                tmp = ConfigModel.combine_configs(orig_dict.get(key, {}), val)
                orig_dict[key] = tmp
            else:
                orig_dict[key] = new_dict[key]
        return orig_dict


class PartialLoadConfig(ConfigModel):
    """Models that have partial models which requires a context to properly load."""

    # [Using validation context with BaseModel initialization](https://docs.pydantic.dev/2.3/usage/validators/#using-validation-context-with-basemodel-initialization)
    def __init__(__pydantic_self__, **data: Any) -> None:
        __pydantic_self__.__pydantic_validator__.validate_python(
            data,
            self_instance=__pydantic_self__,
            context=_init_context_var.get(),
        )

    @classmethod
    def path_relative_to_absolute(cls, value: Path, info: ValidationInfo) -> Path:
        if info.context and value is not None and not value.is_absolute():
            config_path = info.context.get("config_path", Path("."))
            value = (config_path.parent / value).resolve()
        return value


class LoggerConfig(PartialLoadConfig):
    """The logger configures all the information needed for where to store your experiment's logs and checkpoints.
    The structure of your logs will then be:
    <name> / <version> / <sub_dir>
    <sub_dir> will be generated by calling <sub_dir_callable> each time the LoggerConfig is constructed.
    """

    name: str = Field(
        "BaseExperiment",
        title="Experiment Name",
        description="The name of the experiment. The structure of your logs will be <name> / <version> / <sub_dir>.",
    )

    save_dir: DirectoryPath = Field(
        Path("./logs_and_checkpoints"),
        description="The directory to save your checkpoints and logs to.",
    )

    sub_dir_callable: PossiblySerializedCallable = Field(
        get_current_time,
        description="The function that generates a string to call your runs - by default this is a timestamp. The structure of your logs will be <name> / <version> / <sub_dir> where <sub_dir> is a timestamp.",
    )

    version: str = Field(
        "base",
        description="The version of your experiment. The structure of your logs will be <name> / <version> / <sub_dir>.",
    )

    @field_validator("save_dir", mode="before")
    @classmethod
    def relative_to_absolute(cls, value: Any, info: ValidationInfo) -> Path:
        if not isinstance(value, Path):
            try:
                value = Path(value)
            except TypeError as e:
                # Pydantic needs ValueErrors to raise its ValidationErrors
                raise ValueError from e
        absolute_dir = cls.path_relative_to_absolute(value, info)
        if not absolute_dir.exists():
            logger.info(f"Directory at {absolute_dir} does not exist. Creating...")
            absolute_dir.mkdir(parents=True, exist_ok=True)
        return absolute_dir

    @cached_property
    def sub_dir(self) -> str:
        return self.sub_dir_callable()


class BaseTrainingConfig(PartialLoadConfig):
    batch_size: int = Field(
        16,
        description="The number of samples to include in each batch when training. If you are running out of memory, consider lowering your batch_size.",
    )
    save_top_k_ckpts: int = Field(5, description="The number of checkpoints to save.")
    # According to
    # [ModelCheckpoint](https://lightning.ai/docs/pytorch/stable/api/lightning.pytorch.callbacks.ModelCheckpoint.html#lightning.pytorch.callbacks.ModelCheckpoint),
    # ckpt_epochs and ckpt_steps must be None or non-negative.
    # 0 is the same as None, and disables checkpointing
    ckpt_steps: Union[Annotated[int, Field(ge=0)], None] = Field(
        None,
        description="The interval (in steps) for saving a checkpoint. By default checkpoints are saved every epoch using the 'ckpt_epochs' hyperparameter",
    )
    ckpt_epochs: Union[Annotated[int, Field(ge=0)], None] = Field(
        1,
        description="The interval (in epochs) for saving a checkpoint. You can also save checkpoints after n steps by using 'ckpt_steps'",
    )
    check_val_every_n_epoch: int = Field(
        1,
        description="Run validation after every n epochs. Defaults to 1, but if you have a small dataset you should change this to be larger to speed up training",
    )
    max_epochs: int = Field(1000, description="Stop training after this many epochs")
    max_steps: int = Field(100000, description="Stop training after this many steps")
    finetune_checkpoint: Union[PossiblyRelativePath, None] = Field(
        None,
        description="Automatically resume training from a checkpoint loaded from this path.",
    )
    training_filelist: PossiblyRelativePath = Field(
        Path("./path/to/your/preprocessed/training_filelist.psv"),
        description="The path to a filelist containing samples belonging to your training set.",
    )
    validation_filelist: PossiblyRelativePath = Field(
        Path("./path/to/your/preprocessed/validation_filelist.psv"),
        description="The path to a filelist containing samples belonging to your validation set.",
    )
    filelist_loader: PossiblySerializedCallable = Field(
        generic_dict_loader,
        description="Advanced. The function to use to load the filelist.",
    )
    logger: LoggerConfig = Field(
        default_factory=LoggerConfig,
        description="The configuration for the logger.",
    )
    val_data_workers: int = Field(
        0,
        description="The number of CPU workers to use when loading data during validation.",
    )
    train_data_workers: int = Field(
        4,
        description="The number of CPU workers to use when loading data during training.",
    )

    @field_validator("training_filelist", "validation_filelist")
    @classmethod
    def relative_to_absolute(cls, value: Path, info: ValidationInfo) -> Path:
        return PartialLoadConfig.path_relative_to_absolute(value, info)

    @model_validator(mode="after")
    def multually_exclusive_ckpt_options(self) -> "BaseTrainingConfig":
        """
        As documented in
        [ModelCheckpoint](https://lightning.ai/docs/pytorch/stable/api/lightning.pytorch.callbacks.ModelCheckpoint.html#lightning.pytorch.callbacks.ModelCheckpoint),
        `ckpt_steps` and `ckpt_epochs` have to be mutually exclusive.
        """
        if self.ckpt_epochs is not None and self.ckpt_steps is not None:
            raise ValueError("ckpt_epochs and ckpt_steps have to be mutually exclusive")
        return self


class BaseOptimizer(ConfigModel):
    learning_rate: float = Field(1e-4, description="The initial learning rate to use")
    eps: float = Field(
        1e-8,
        description="Advanced. The value of optimizer constant Epsilon, used for numerical stability.",
    )
    weight_decay: float = 0.01


class RMSOptimizer(BaseOptimizer):
    alpha: float = Field(
        0.99,
        description="Advanced. The value of RMSProp optimizer alpha smoothing constant.",
    )
    name: str = Field("rms", description="The name of the optimizer to use.")


class AdamOptimizer(BaseOptimizer):
    betas: Tuple[float, float] = Field(
        (0.9, 0.98),
        description="Advanced. The values of the Adam Optimizer beta coefficients.",
    )
    name: str = Field("adam", description="The name of the optimizer to use.")


class AdamWOptimizer(BaseOptimizer):
    betas: Tuple[float, float] = Field(
        (0.9, 0.98),
        description="Advanced. The values of the AdamW Optimizer beta coefficients.",
    )
    name: str = Field("adamw", description="The name of the optimizer to use.")


class NoamOptimizer(AdamOptimizer):
    warmup_steps: int = Field(
        4000,
        description="The number of steps to increase the learning rate before starting to decrease it.",
    )
    name: str = Field("noam", description="The name of the optimizer to use.")
