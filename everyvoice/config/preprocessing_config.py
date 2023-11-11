from enum import Enum
from pathlib import Path
from typing import Annotated, Any, List, Optional, Union

from annotated_types import Ge, Le
from loguru import logger
from pydantic import Field, FilePath, ValidationInfo, field_validator, model_validator

from everyvoice.config.shared_types import ConfigModel, PartialLoadConfig, init_context
from everyvoice.config.utils import (
    PossiblyRelativePath,
    PossiblySerializedCallable,
    load_partials,
)
from everyvoice.utils import generic_dict_loader, load_config_from_json_or_yaml_path


class AudioSpecTypeEnum(Enum):
    mel = "mel"  # TorchAudio implementation
    mel_librosa = "mel-librosa"  # Librosa implementation
    linear = "linear"  # TorchAudio Linear Spectrogram
    raw = "raw"  # TorchAudio Complex Spectrogram


class AudioConfig(ConfigModel):
    min_audio_length: float = Field(
        0.4,
        description="The minimum length of an audio sample in seconds. Audio shorter than this will be ignored during preprocessing.",
    )
    max_audio_length: float = Field(
        11.0,
        description="The maximum length of an audio sample in seconds. Audio longer than this will be ignored during preprocessing.",
    )
    max_wav_value: float = Field(
        32767.0,
        description="Advanced. The maximum value allowed to be in your wav files. For 16-bit audio, this should be (2**16)/2 - 1.",
    )
    input_sampling_rate: int = Field(
        22050,
        description="The sampling rate describes the number of samples per second of audio. The 'input_sampling_rate' is with respect to your vocoder, or spec-to-wav model. This means that the spectrograms predicted by your text-to-spec model will also be calculated from audio at this sampling rate. If you change this value, your audio will automatically be re-sampled during preprocessing.",
    )
    output_sampling_rate: int = Field(
        22050,
        description="Advanced. The sampling rate describes the number of samples per second of audio. The 'output_sampling_rate' is with respect to your vocoder, or spec-to-wav model. This means that the wav files generated by your vocoder or spec-to-wav model will be at this sampling rate. If you change this value, you will also need to change the upsample rates in your vocoder. Your audio will automatically be re-sampled during preprocessing.",
    )
    alignment_sampling_rate: int = Field(
        22050,
        description="Advanced. The sampling rate describes the number of samples per second of audio. The 'alignment_sampling_rate' describes the sampling rate used when training an alignment model. If you change this value, your audio will automatically be re-sampled during preprocessing.",
    )
    target_bit_depth: int = Field(
        16,
        description="Advanced. This is the bit depth of each sample in your audio files.",
    )
    n_fft: int = Field(
        1024, title="FFT Size", description="Advanced. This is the size of the FFT."
    )
    fft_window_size: int = Field(
        1024,
        title="FFT Window Size",
        description="Advanced. This is the window size of the FFT.",
    )
    fft_hop_size: int = Field(
        256,
        title="FFT Hop Size",
        description="Advanced. This is the hop size for calculating the Short-Time Fourier Transform which calculates a sequence of spectrograms from a single audio file. Another way of putting it is that the hop size is equal to the amount of non-intersecting samples from the audio in each spectrogram.",
    )
    f_min: int = Field(
        0,
        title="Minimum Frequency",
        description="Advanced. This is the minimum frequency for the lowest frequency bin when calculating the spectrogram.",
    )
    f_max: int = Field(
        8000,
        title="Maximum Frequency",
        description="Advanced. This is the maximum frequency for the highest frequency bin when calculating the spectrogram.",
    )
    n_mels: int = Field(
        80,
        title="Number of Mel bins",
        description="Advanced. This is the number of filters in the Mel-scale spaced filterbank.",
    )
    spec_type: Union[AudioSpecTypeEnum, str] = Field(
        AudioSpecTypeEnum.mel_librosa.value,
        description="Advanced. Defines how to calculate the spectrogram. 'mel' uses the TorchAudio implementation for a Mel spectrogram. 'mel-librosa' use's Librosa's implementation. 'linear' calculates a non-Mel linear spectrogram and 'raw' calculates a complex-valued spectrogram.",
    )
    vocoder_segment_size: int = Field(
        8192,
        description="Advanced. The vocoder, or spec-to-wav model is trained by sampling random fixed-size sections of the audio. This value specifies the number of samples in those sections.",
    )


class PitchCalculationMethod(Enum):
    pyworld = "pyworld"
    cwt = "cwt"


class Dataset(PartialLoadConfig):
    label: str = Field("YourDataSet", description="The name of your dataset")
    data_dir: PossiblyRelativePath = Field(
        Path("/please/create/a/path/to/your/dataset/data"),
        description="The path to the directory with your audio files.",
    )
    filelist: PossiblyRelativePath = Field(
        Path("/please/create/a/path/to/your/dataset/filelist"),
        description="The path to your dataset's filelist.",
    )
    filelist_loader: PossiblySerializedCallable = Field(
        generic_dict_loader,
        description="Advanced. The file-loader function to use to load your dataset's filelist.",
    )
    sox_effects: list = Field(
        [["channels", "1"]],
        description="Advanced. A list of SoX effects to apply to your audio prior to preprocessing. Run torchaudio.sox_effects.effect_names() in a Python interpreter to see a list of supported effects.",
    )

    @field_validator(
        "data_dir",
        "filelist",
    )
    @classmethod
    def relative_to_absolute(cls, value: Path, info: ValidationInfo) -> Path:
        return PartialLoadConfig.path_relative_to_absolute(value, info)


class PreprocessingConfig(PartialLoadConfig):
    dataset: str = "YourDataSet"
    pitch_type: Union[
        PitchCalculationMethod, str
    ] = PitchCalculationMethod.pyworld.value
    pitch_phone_averaging: bool = True
    energy_phone_averaging: bool = True
    value_separator: str = "--"
    train_split: Annotated[float, Ge(0.0), Le(1.0)] = 0.9
    dataset_split_seed: int = 1234
    save_dir: PossiblyRelativePath = Path("./preprocessed/YourDataSet")
    audio: AudioConfig = Field(default_factory=AudioConfig)
    path_to_audio_config_file: Optional[FilePath] = None
    source_data: List[Dataset] = Field(default_factory=lambda: [Dataset()])

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

    @model_validator(mode="before")  # type: ignore
    def load_partials(self, info: ValidationInfo):
        config_path = (
            info.context.get("config_path", None) if info.context is not None else None
        )
        return load_partials(
            self,  # type: ignore
            ("audio",),
            config_path=config_path,
        )

    @staticmethod
    def load_config_from_path(path: Path) -> "PreprocessingConfig":
        """Load a config from a path"""
        config = load_config_from_json_or_yaml_path(path)
        with init_context({"config_path": path}):
            config = PreprocessingConfig(**config)
        return config
