import argparse
import torch
import glob
import numpy as np
from torchvision.transforms import transforms
from PIL import Image
from typing import Union, Generator, Tuple



class Env():
    def __init__(self, model_name: str = "mobilenet", mode: str = "train", feature_extract_layer: int = 4) -> None:
        self.state: Tuple[np.ndarray, np.ndarray] = None # current state (image, featuremap)
        self.target_label: int = None
        self.episode: int = None # current episode (integer)
        self.prev_confidence_score: float = None

        self.image_model: torch.nn.Module = None

        self.model_name: str = model_name

        self.permutation_list: np.ndarray = None

        self.train_dataset: dict = None
        self.val_dataset: dict = None
        self.test_dataset: dict = None

        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0, 0, 0), (1, 1, 1))
        ])

        self.mode = mode
        self.feature_extract_layer = feature_extract_layer

    # return permutation list
    def _make_permutation_list(self, n) -> np.ndarray:
        """ 
        _make_permutation_list 함수는 [0,n-1] 에 속하는 정수로 permutation vector를 반환합니다.
        
        input 
            n : 만들고 싶은 permutation vector의 길이
        output
            없음 
        """
        self.permutation_list = np.random.permutation(n)

    def _load_dataset(self) -> None:
        """ 
        _load_dataset 함수는 original image와 perturbed 이미지를 불러옵니다.
        self.mode에 따라서 train, val, test으로 서로 다른 데이터셋을 self.train_dataset, self.val_dataset, self.test_dataset 에 로드합니다.
        """
        origin_images_paths = glob.glob(f"images/{self.model_name}/origin/{self.mode}")
        perturbed_images_paths = glob.glob(f"images/{self.model_name}/adv/{self.mode}")

        data_num = len(origin_images_paths)

        self._make_permutation_list(n = data_num)
        
        origin_images = (self._return_transform_image(path) for path in origin_images_paths)
        perturbed_images = (self._return_transform_image(path) for path in perturbed_images_paths)

        if self.mode == "train":
            self.train_dataset = {"origin_images" : origin_images, "perturbed_images" : perturbed_images}

        elif self.mode == "val":
            self.val_dataset = {"origin_images" : origin_images, "perturbed_images" : perturbed_images}

        elif self.mode == "test":
            self.test_dataset = {"origin_images" : origin_images, "perturbed_images" : perturbed_images}


    def _return_transform_image(self, image_path: str) -> torch.Tensor:
        with Image.open(image_path) as img:
            return self.transform(img)
    
    
    def _get_next_image_label(self) -> Union[Tuple[torch.Tensor, torch.Tensor, int], int]:
        """
        _get_next_image_label 함수는 현재 선택된 데이터셋에서 다음 이미지의 original, perturbed, class를 반환합니다. 
        self.mode에 따라서 self.train_dataset, self.val_dataset, self.test_dataset 에서 데이터를 가져옵니다.

        input:
            없음
        output:
            (origin_image_tensor, perturbed_image_tensor, image_label)
        """
        try:
            if self.mode == "train":
                dataset = self.train_dataset

            elif self.mode == "val":
                dataset = self.val_dataset

            elif self.mode == "test":
                dataset = self.test_dataset
                
            origin_images = dataset["origin_images"]
            perturbed_images = dataset["perturbed_images"]

            origin_image_path = next(origin_images, None)
            perturbed_image_path = next(perturbed_images, None)

            if origin_image_path is None and perturbed_image_path is None:
                return -1
            
            origin_image_tensor: torch.Tensor = self.transform(origin_image_path)
            perturbed_image_tensor: torch.Tensor = self.transform(perturbed_image_path)

            image_label: int = int(perturbed_image_path.split("_")[1])

            if image_label != int(origin_image_path.split("_")[1]):
                raise ValueError("The original class of the original image and the perturbed image is different.")

            return (origin_image_tensor, perturbed_image_tensor, image_label)
        
        except Exception as e:
            raise e
        
    

    def _inference(self, image: torch.Tensor = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        _inference 함수는 입력에 대한 target DNN 모델의 confidence score와 중간 feature를 반환합니다.

        input:
            image: 추론을 진행할 torch.Tensor 이미지
        output:
            (confidence score, feature map)
        """
        self.image_model(image)

    def _defense_image(self, channel: int, index: int, std: float) -> None:
        """
        _defense_image 함수는 주어진 target pixel(index)에 std를 가진 noise를 추가합니다.

        input:
            - channel (int): 변형할 이미지의 channel (0: R, 1: G, 2: B)
            - index (int): 변형할 image의 index vector
            - std (float): defense perturbation의 standard deviation
        """
        y = index / self.size
        x = index % self.size
        # self.state[0][channel, y, x]을 중심으로 std만큼 바꿔야됨

        

    def _get_reward(self, confidence_score: np.ndarray) -> float:
        """
        _get_reward 함수는 이미지 모델의 추론에 대한 confidence drift의 정도를 반환합니다.

        input:
            - confidence_score (np.ndarray): 갱신된 confidence_score
        output:
            - reward (float): action을 수행했을 때의 reward를 반환합니다. Reward는 image model의 confidence drift입니다.
        """
        target_drift = confidence_score - self.prev_confidence_score
        non_target_drift = np.delete(confidence_score, self.target_label) - np.delete(self.prev_confidence_score, self.target_label)
        result = target_drift - self.alpha * non_target_drift

        return result
                

    def train(self) -> None:
        self.mode = "train"

        if self.train_dataset is None:
            self._load_dataset()

    def val(self) -> None:
        self.mode = "val"

        if self.val_dataset is None:
            self._load_dataset()

    def test(self) -> None:
        self.mode = "test"

        if self.test_dataset is None:
            self._load_dataset()
        

    def reset(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        reset 함수는 state, episode, prev_confidence_score, dataset을 초기화 하고, state를 반환합니다.
        self.mode에 따라 state가 불러와지는 dataset이 달라집니다.

        input:
            없음
        output:
            (image: np.ndarray, feature_map: np.ndarray)
        """
        self._load_dataset()
        origin_image_tensor, perturbed_image_tensor, image_label = self._get_next_image_label()
        pass

    def step(self, action: Tuple[np.ndarray, np.ndarray]) -> Tuple[Tuple[np.ndarray, np.ndarray], float, bool, bool, None]:
        """
        step 함수는 environment에 행할 action을 받아 해당 action을 진행했을 때의 state, reward, termination 여부를 반환합니다.

        input:
            - action (channel: int, index: int, std: float)
                - channel (int): 변형할 이미지의 channel (0: R, 1: G, 2: B)
                - index (int): 변형할 이미지의 pixel index
                - std (float) perturbation standard deviation
        output:
            - state (image: np.ndarray, feature_map: np.ndarray): action이 수행된 이후의 image array와 해당 array의 feature map을 반환합니다.
            - reward (float): action을 수행했을 때의 reward를 반환합니다. Reward는 image model의 confidence drift입니다.
            - terminated (bool): agent가 episode의 terminal state에 도착했는지의 여부입니다.
            - truncated (bool): agent가 episode 도중 truncation condition에 의해 중단되었는지의 여부입니다.
            - info (None): None을 반환합니다.
        """
        channel, index, std = action
        state = (np.zeros(1), np.zeros(1))
        terminated = False
        truncated = False

        # Defense image with action
        self._defense_image(channel, index, std)

        # Inference image, get new confidence score
        confidence_score, feature_map = self._inference()

        # Calculate confidence drift
        reward = self._get_reward(confidence_score)

        # Update informations
        self.state[1] = feature_map
        self.prev_confidence_score = confidence_score

        return state, reward, terminated, truncated, None