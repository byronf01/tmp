import os
import sys
import numpy as np
import torch
from pathlib import Path
from typing import List, Dict, Tuple
from copy import deepcopy
from torch.utils.data import Dataset
import re

# import relative packages
sys.path.append(".")
from src.preprocessing.subtile_esd_hw02 import Subtile, TileMetadata


class DSE(Dataset):
    """
    Custom dataset for the IEEE GRSS 2021 ESD dataset.

    args:
        root_dir: str | os.PathLike
            Location of the processed subtiles
        selected_bands: Dict[str, List[str]] | None
            Dictionary mapping satellite type to list of bands to select
        transform: callable, optional
            Object that applies augmentations to a sample of the data
    attributes:
        root_dir: str | os.PathLike
            Location of the processed subtiles
        tiles: List[Path]
            List of paths to the subtiles
        transform: callable
            Object that applies augmentations to the sample of the data

    """

    def __init__(
        self,
        root_dir: str | os.PathLike,
        selected_bands: Dict[str, List[str]] | None = None,
        transform=None,
    ):
        self.root_dir = root_dir
        self.selected_bands = selected_bands
        self.transform = transform

        self.tiles = [
            Path(file_name) for file_name in list(Path(self.root_dir).glob("*.npz"))
        ]

    def __len__(self):
        """
        Returns number of tiles in the dataset

        Output: int
            length: number of tiles in the dataset
        """
        return len(self.tiles)

    def __aggregate_time(self, img):
        """
        Aggregates time dimension in order to
        feed it to the machine learning model.

        This function needs to be changed in the
        final project to better suit your needs.

        For homework 2, you will simply stack the time bands
        such that the output is shaped (time*bands, width, height),
        i.e., all the time bands are treated as a new band.

        Input:
            img: np.ndarray
                (time, bands, width, height) array
        Output:
            new_img: np.ndarray
                (time*bands, width, height) array
        """
        return np.reshape(
            img, (img.shape[0] * img.shape[1], img.shape[2], img.shape[3])
        )

    def __select_indices(self, bands: List[str], selected_bands: List[str]):
        """
        Selects the indices of the bands used.

        Input:
            bands: List[str]
                list of bands in the order that they are stacked in the
                corresponding satellite stack
            selected_bands: List[str]
                list of bands that have been selected

        Output:
            bands_indices: List[int]
                index location of selected bands
        """
        return [index for index, value in enumerate(bands) if value in selected_bands]

    def __select_bands(self, subtile):
        """
        Aggregates time dimension in order to
        feed it to the machine learning model.

        This function needs to be changed in the
        final project to better suit your needs.

        For homework 2, you will simply stack the time bands
        such that the output is shaped (time*bands, width, height),
        i.e., all the time bands are treated as a new band.

        Input:
            subtile: Subtile object
                (time, bands, width, height) array
        Output:
            selected_satellite_stack: Dict[str, np.ndarray]
                satellite--> np.ndarray with shape (time, bands, width, height) array

            new_metadata: TileMetadata
                Updated metadata with only the satellites and bands that were picked
        """
        new_metadata = deepcopy(subtile.tile_metadata)
        if self.selected_bands is not None:
            selected_satellite_stack = {}
            new_metadata.satellites = {}
            for key in self.selected_bands:
                satellite_bands = subtile.tile_metadata.satellites[key].bands
                selected_bands = self.selected_bands[key]
                indices = self.__select_indices(satellite_bands, selected_bands)
                new_metadata.satellites[key] = subtile.tile_metadata.satellites[key]
                subtile.tile_metadata.satellites[key].bands = self.selected_bands[key]
                # for i in indices:
                #   selected_satellite_stack[key][:, i, :, :] = subtile.satellite_stack[key][:, i, :, :]
                selected_satellite_stack[key] = subtile.satellite_stack[key][
                    :, indices, :, :
                ]  # dimensions [t, bands, h, w]
        else:
            selected_satellite_stack = subtile.satellite_stack

        return selected_satellite_stack, new_metadata

    def __getitem__(self, idx: int) -> Tuple[np.ndarray, np.ndarray, TileMetadata]:
        """
        Loads subtile at index idx, then
            - selects bands
            - aggregates times
            - stacks satellites
            - performs self.transform

        Input:
            idx: int
                index of subtile with respect to self.tiles

        Output:
            X: np.ndarray | torch.Tensor
                input data to ML model, of shape (time*bands, width, height)
            y: np.ndarray | torch.Tensor
                ground truth, of shape (1, width, height)
            tile_metadata:
                corresponding tile metadata
        """
        # load the subtiles using the Subtile class in
        # src/preprocessing/subtile_esd_hw02.py
        subtile = Subtile().load(self.tiles[idx])

        # call the __select_bands function to select the bands and satellites
        X, y = list(), None
        satellite_stack, metadata = self.__select_bands(subtile)
        y = subtile.satellite_stack["gt"]

        # stack the time dimension with the bands, this will treat the
        # timestamps as bands for the model you may want to change this
        # depending on your model and depending on which timestamps and
        # bands you want to use
        for satellite_type, stack in satellite_stack.items():
            if satellite_type != "gt":
                X = (
                    self.__aggregate_time(stack)
                    if len(X) == 0
                    else np.concatenate((X, self.__aggregate_time(stack)))
                )

        # Concatenate the time and bands

        # Adjust the y ground truth to be the same shape as the X data by
        # removing the time dimension
        y = np.squeeze(y, axis=0)

        # all timestamps are treated and stacked as bands

        # if there is a transform, apply it to both X and y
        if self.transform != None:
            transformed = self.transform({"X": X, "y": y})
            X, y = transformed["X"], transformed["y"]

        return (X, y - 1, metadata)
    

    def find_subtile(self, tile_id, i, j):
        """
        Equivalent of __getitem__ except it searches for a given
        Tile{tile_id}_{i}_{j}.npz file.

        Input:
            tile_id: int
                Parent tile ID
            i: int
                The i-th subtile along the width
            j: int
                The j-th subtile along the height
        
        Output:
            Same return as __getitem__
        """
        pattern = re.compile('Tile(\d+)_(\d+)_(\d+).npz')
        
        for k, subtile in enumerate(self.tiles):
            result = pattern.search(subtile.name)
            id_value, x, y = result.group(1), result.group(2), result.group(3)
            
            if tile_id == int(id_value) and i == int(x) and j == int(y):
                return self.__getitem__(k)
        
        raise ValueError(f'Could not find Tile{tile_id}_{i}_{j}.npz in the dataset')
