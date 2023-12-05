import torch
from torch import nn
from tqdm import tqdm
import numpy as np

from test_methods.TesterBase import TesterBase

class Tester(TesterBase):
    def __init__(self, agent: nn.Module, env, conf, manager, agent_path = None) -> None:
        super(Tester, self).__init__(agent, env, conf, manager, agent_path)

    def test(self):
        # Hyper-parameter
        num_episode = self.conf["num_episode"]
        num_step = self.conf["num_step"] 
        mode = self.conf["mode"]
        rand = self.conf["rand"]
        print_interval = 100
        save_interval = 100

        self.env.train()
        
        # Train code
        total_reward = 0
        
        for episode in tqdm(range(num_episode)):
            epi_reward = 0
            state, _ = self.env.reset()
            initial_state = state.copy()
            initial_confidence, _ = self.env.inference()
            initial_label = torch.argmax(initial_confidence)
            if episode%save_interval==0:
                if self.conf['image_save']:
                    self.manager.save_image(episode, 0, state[0]) # 변화 없는 이미지 = 0
                if self.conf['action_logger']:
                    self.manager.save_action(episode, 0, [], [], [], epi=True)
            done = False
            ents = [] # entropies
            for step in range(num_step):
                actions, action_probs, entropies = self.agent.get_actions(state, rand=rand)
                ents.append(np.array(entropies))
                
                state_prime, reward, terminated, truncated, info = self.env.step(actions)
                if terminated or truncated :
                    done = True
                self.agent.put_data((state, actions, reward, state_prime, action_probs, done))
                reward = reward.item()
                epi_reward += reward
                state = state_prime
                if episode%save_interval==0:
                    if self.conf['image_save']:
                        self.manager.save_image(episode, step+1, state[0])
                    if self.conf['action_logger']:
                        self.manager.save_action(episode, step+1, actions, action_probs, entropies, epi=False)
                if done :
                    step_confidence, _ = self.env.inference()
                    step_label = torch.argmax(step_confidence)
                    if initial_label == step_label:
                        state = initial_state
                    break
            ents = np.mean(ents, axis=0)
            for idx, ent in enumerate(ents):
                self.manager.record(f'{mode}/entropy/action{idx}', ent, episode)
            total_reward += epi_reward

            # record total_reward & avg_reward & loss for each episode
            self.manager.record(mode+"/total_reward", epi_reward, episode)
            self.manager.record(mode+"/avg_reward", (epi_reward/(step+1)), episode)

            loss, value_loss, policy_loss = self.agent.train_net()
        
            if loss is not None :
                self.manager.record(mode+"/loss", loss.mean(), episode)
                self.manager.record(mode+"/value_loss", sum(value_loss).mean().item(), episode)
                self.manager.record(mode+"/policy_loss", sum(policy_loss).mean().item(), episode)
            if episode % print_interval == 0 and step != 0:
                print("\n# of episode :{}, avg reward : {:.2f}, total reward : {:.2f}".format(episode, total_reward/print_interval, total_reward))
                total_reward = 0