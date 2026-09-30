import os
import time
import typing as t

from huggingface_hub import InferenceClient
import openai
from mistralai.client import Mistral
from _types import Message, Parameters, Role
from openai import OpenAI, RateLimitError, APIStatusError
from openai.types.chat import ChatCompletionMessageParam


def _chat_openai(
    client: OpenAI, messages: t.List[Message], parameters: Parameters
) -> Message:
    while True:
        try:
            response = client.chat.completions.create(
                model=parameters.model,
                messages=t.cast(t.List[ChatCompletionMessageParam], messages),
                temperature=parameters.temperature,
                max_tokens=parameters.max_tokens,
                top_p=parameters.top_p,
            )

            response_message = response.choices[0].message

            return Message(
                role=Role(response_message.role),
                content=str(response_message.content),
            )

        except RateLimitError:
            print("[!] OpenAI rate limit (429). Retrying in 60 seconds...")
            time.sleep(60)

        except APIStatusError as e:
            # Some OpenAI-compatible providers return 402
            # for insufficient balance/credits.
            if e.status_code == 402:
                print("[!] API credits exhausted (402). Retrying in 60 seconds...")
                time.sleep(60)


def chat_openai(messages: t.List[Message], parameters: Parameters) -> Message:
    return _chat_openai(OpenAI(), messages, parameters)


def chat_mistral(
    messages: t.List[Message],
    parameters: Parameters,
) -> Message:

    client = Mistral(
        api_key=os.environ["MISTRAL_API_KEY"]
    )

    mistral_messages = [
        {
            "role": message.role.value
            if isinstance(message.role, Role)
            else str(message.role),
            "content": message.content,
        }
        for message in messages
    ]

    response = client.chat.complete(
        model=parameters.model,
        messages=mistral_messages,
        temperature=parameters.temperature,
        max_tokens=parameters.max_tokens,
        top_p=parameters.top_p,
    )

    response_message = response.choices[-1].message

    return Message(
        role=Role(response_message.role),
        content=str(response_message.content),
    )


def embed_mistral(contents: t.List[str]) -> t.List[t.List[float]]:

    client = Mistral(
        api_key=os.environ["MISTRAL_API_KEY"]
    )

    response = client.embeddings.create(
        model="mistral-embed",
        inputs=contents,
    )

    return [d.embedding for d in response.data]

def chat_together(messages: t.List[Message], parameters: Parameters) -> Message:
    client = openai.OpenAI(
        api_key=os.environ["TOGETHER_API_KEY"],
        base_url="https://api.together.xyz/v1",
    )

    return _chat_openai(client, messages, parameters)

def chat_huggingface(
    messages: t.List[Message],
    parameters: Parameters,
) -> Message:
    client = openai.OpenAI(
        api_key=os.environ["HUGGINGFACE_API_KEY"],
        base_url="https://router.huggingface.co/v1",
    )

    return _chat_openai(client, messages, parameters)

def chat_openrouter(
    messages: t.List[Message],
    parameters: Parameters,
) -> Message:
    client = openai.OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )

    return _chat_openai(client, messages, parameters)