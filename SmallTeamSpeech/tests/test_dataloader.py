from unittest import TestCase

from config.base_config import BaseConfig
from dataloader import BaseDataModule, HiFiGANDataModule, SpecDataset


class DataLoaderTest(TestCase):
    """Basic test for dataloaders"""

    def setUp(self) -> None:
        self.config = BaseConfig()

    def test_base_data_loader(self):
        bdm = BaseDataModule(self.config)
        with self.assertRaises(NotImplementedError):
            bdm.load_dataset()

    def test_spec_dataset(self):
        dataset = SpecDataset(
            self.config["training"]["vocoder"]["filelist_loader"](
                self.config["training"]["vocoder"]["filelist"]
            ),
            self.config,
            use_segments=True,
        )
        for sample in dataset:
            spec, audio, basename, spec_from_audio = sample
            self.assertTrue(isinstance(basename, str))
            self.assertEqual(spec.size(), spec_from_audio.size())
            self.assertEqual(
                spec.size(0), self.config["preprocessing"]["audio"]["n_mels"]
            )
            self.assertEqual(
                spec.size(1),
                self.config["preprocessing"]["audio"]["vocoder_segment_size"]
                / (
                    self.config["preprocessing"]["audio"]["fft_hop_frames"]
                    * (
                        self.config["preprocessing"]["audio"]["output_sampling_rate"]
                        // self.config["preprocessing"]["audio"]["input_sampling_rate"]
                    )
                ),
            )

    def test_hifi_data_loader(self):
        hfgdm = HiFiGANDataModule(self.config)
        hfgdm.load_dataset()
        self.assertEqual(len(hfgdm.dataset), 5)

    def test_hifi_ft_data_loader(self):
        """TODO: can't make this test until I generate some synthesized samples"""
        pass

    def test_feature_prediction_data_loader(self):
        # TODO: once feature prediction is done
        pass

    def test_e2e_data_module(self):
        # TODO: once e2e is done
        pass
