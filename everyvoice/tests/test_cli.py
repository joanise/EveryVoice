#!/usr/bin/env python

import json
import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main

import jsonschema
import yaml
from typer.testing import CliRunner
from yaml import CLoader as Loader

# required for `./run_tests.py cli` to work, otherwise test_inspect_checkpoint
# fails with an Intel MKL FATAL ERROR saying it cannot load libtorch_cpu.so
import everyvoice.tests.test_model  # noqa
from everyvoice import __file__ as EV_FILE
from everyvoice.base_cli.helpers import save_configuration_to_log_dir
from everyvoice.cli import SCHEMAS_TO_OUTPUT, app
from everyvoice.model.feature_prediction.FastSpeech2_lightning.fs2.config import (
    FastSpeech2Config,
)
from everyvoice.tests.stubs import mute_logger

EV_DIR = Path(EV_FILE).parent


class CLITest(TestCase):
    data_dir = Path(__file__).parent / "data"

    def setUp(self) -> None:
        self.runner = CliRunner()
        self.commands = [
            "new-project",
            "train",
            "synthesize",
            "preprocess",
            "inspect-checkpoint",
        ]

    def test_commands_present(self):
        result = self.runner.invoke(app, ["--help"])
        # each command has some help
        for command in self.commands:
            self.assertIn(command, result.stdout)
        # link to docs is present
        self.assertIn("https://docs.everyvoice.ca", result.stdout)

    def test_command_help_messages(self):
        for command in self.commands:
            result = self.runner.invoke(app, [command, "--help"])
            self.assertEqual(result.exit_code, 0)
            result = self.runner.invoke(app, [command, "-h"])
            self.assertEqual(result.exit_code, 0)

    def test_update_schema(self):
        result = self.runner.invoke(app, ["update-schemas"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("FileExistsError", str(result))
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.runner.invoke(app, ["update-schemas", "-o", tmpdir])
            for filename, obj in SCHEMAS_TO_OUTPUT.items():
                with open(Path(tmpdir) / filename, encoding="utf8") as f:
                    schema = json.load(f)
                # serialize the model to json and then validate against the schema
                self.assertIsNone(
                    jsonschema.validate(
                        json.loads(obj().model_dump_json()), schema=schema
                    )
                )

    def test_inspect_checkpoint_help(self):
        result = self.runner.invoke(app, ["inspect-checkpoint", "--help"])
        self.assertIn("inspect-checkpoint [OPTIONS] MODEL_PATH", result.stdout)

    def test_inspect_checkpoint(self):
        result = self.runner.invoke(
            app, ["inspect-checkpoint", str(self.data_dir / "test.ckpt")]
        )
        self.assertIn('global_step": 52256', result.stdout)
        self.assertIn(
            "We couldn't read your file, possibly because the version of EveryVoice that created it is incompatible with your installed version.",
            result.stdout,
        )
        self.assertIn("It appears to have 0.0 M parameters.", result.stdout)
        self.assertIn("Number of Parameters", result.stdout)


class TestBaseCLIHelper(TestCase):
    """ """

    def test_save_configuration_to_log_dir(self):
        """ """
        with TemporaryDirectory() as tempdir, mute_logger(
            "everyvoice.base_cli.helpers"
        ):
            tempdir = Path(tempdir)
            config = FastSpeech2Config(
                **{
                    "training": {
                        "logger": {
                            "save_dir": tempdir / "log",
                            "name": "unittest",
                        },
                    },
                }
            )
            save_configuration_to_log_dir(config)

            log_dir = config.training.logger.save_dir / config.training.logger.name
            log = log_dir / "log"
            self.assertTrue(log.exists())

            hparams = log_dir / "hparams.yaml"
            self.assertTrue(hparams.exists())
            with hparams.open(mode="r", encoding="UTF8") as f:
                config_reloaded = yaml.load(f, Loader=Loader)
                self.assertEqual(
                    config.training.logger.save_dir,
                    Path(config_reloaded["training"]["logger"]["save_dir"]),
                )
                self.assertEqual(
                    config.training.logger.name,
                    config_reloaded["training"]["logger"]["name"],
                )


if __name__ == "__main__":
    main()