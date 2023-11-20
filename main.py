import openai
from openai import OpenAI


openai.api_key = "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"

prompt = """ 
    How do I use SonarCLoud api to evaluate this project?
"""


client = OpenAI(
    api_key="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",
)

res = chat_completion = client.chat.completions.create(
    model="gpt-4-1106-preview",
    # messages = [{"role" : "user", "content": prompt}, {"role" : "user", "content" : requirements}],
    messages=[{"role": "user", "content": prompt}],
    temperature=0,
)


for choice in res.choices:
    message_content = choice.message.content
print(message_content)
