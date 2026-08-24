# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
#
# DeepSeek backend for CompeteAI: OpenAI-compatible chat API served by
# https://api.deepseek.com. Model defaults to `deepseek-chat`.
#
# Environment variable: DEEPSEEK_API_KEY

import os
import re
import time
from typing import List
from tenacity import retry, stop_after_attempt, wait_random_exponential

from .base import IntelligenceBackend
from ...message import Message, SYSTEM_NAME, MODERATOR_NAME
from ...image import Image

try:
    from openai import OpenAI  # v 1.0.0
except ImportError:
    is_deepseek_available = False
else:
    deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_api_key is None:
        is_deepseek_available = False
    else:
        is_deepseek_available = True

total_tokens = 0

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1024

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

END_OF_MESSAGE = "<EOS>"
STOP = ("<|endoftext|>", END_OF_MESSAGE)
BASE_PROMPT = f"The messages always end with the token {END_OF_MESSAGE}."


class DeepSeekChat(IntelligenceBackend):
    """
    Interface to the DeepSeek chat model (OpenAI-compatible endpoint).
    """
    stateful = False
    type_name = "deepseek-chat"

    def __init__(self, temperature: float = DEFAULT_TEMPERATURE, max_tokens: int = DEFAULT_MAX_TOKENS,
                 model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL,
                 merge_other_agents_as_one_user: bool = False, **kwargs):
        assert is_deepseek_available, "openai package is not installed or DEEPSEEK_API_KEY is not set"
        super().__init__(temperature=temperature, max_tokens=max_tokens, model=model,
                         base_url=base_url,
                         merge_other_agents_as_one_user=merge_other_agents_as_one_user, **kwargs)

        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model
        self.base_url = base_url
        self.merge_other_agent_as_user = merge_other_agents_as_one_user

    @retry(stop=stop_after_attempt(6), wait=wait_random_exponential(min=4, max=60))
    def _get_response(self, messages, have_image=False):
        global total_tokens

        client = OpenAI(api_key=deepseek_api_key, base_url=self.base_url)

        completion = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop=STOP
        )

        response = completion.choices[0].message.content
        response = response.strip()
        return response

    def query(self, agent_name: str, agent_type: str, role_desc: str, history_messages: List[Message], relationship: str = None,
              global_prompt: str = None, images: List[Image] = [], request_msg: Message = None, *args, **kwargs) -> str:
        """
        Format the input and call the DeepSeek chat API.
        """
        messages = []

        system_prompt = f" Your name is {agent_name}.\n\nYour role:{role_desc}"
        if global_prompt:  # Prepend the global prompt if it exists
            system_prompt = f"{global_prompt.strip()}\n\n" + system_prompt
        if relationship:
            system_prompt += f"\n\nYour relationship: {relationship.strip()}"
        system_prompt += f"\n\n{BASE_PROMPT}"

        system_message = {"role": "system", "content": system_prompt}
        messages.append(system_message)

        # Text
        if len(history_messages) > 0:
            user_messages = []
            if len(history_messages) > 12:  # context limit
                history_messages = history_messages[-12:]
            for msg in history_messages:
                user_messages.append((msg.agent_name, f"{msg.content}{END_OF_MESSAGE}"))

            user_prompt = ""
            for _, msg in enumerate(user_messages):
                user_prompt += f"[{msg[0]}]: {msg[1]}\n"
            user_prompt += f"You are a {agent_type} in a virtual world. Now it's your turn!"

            user_message = {"role": "user", "content": user_prompt}
            messages.append(user_message)

        # Image
        for image in images:
            image_prompt = [{"type": "text", "text": f"Attached image: {image.owner}-{image.description}"}]
            image_content = f"data:image/jpeg;base64,{image.content}"
            image_content = {"type": "image_url", "image_url": {"url": image_content}}
            image_prompt.append(image_content)
            image_message = {"role": "user", "content": image_prompt}
            messages.append(image_message)

        have_image = True if len(images) > 0 else False

        response = self._get_response(messages, have_image, *args, **kwargs)
        # Remove the agent name if the response starts with it
        response = re.sub(rf"^\s*\[.*]:", "", response).strip()
        response = re.sub(rf"^\s*{re.escape(agent_name)}\s*:", "", response).strip()

        # Remove the tailing end of message token
        response = re.sub(rf"{END_OF_MESSAGE}$", "", response).strip()

        return response
