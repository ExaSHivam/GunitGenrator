import io
import os
import boto3
import pandas as pd
from openpyxl import load_workbook
import openai
from dotenv import load_dotenv
import time
import re
from openai import OpenAI

load_dotenv()

print(os.getenv("OPENAI_API_KEY"))

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AWS_BDD_INPUT_BUCKET = os.getenv("aws_bdd_input_bucket")
AWS_BDD_OUTPUT_BUCKET = os.getenv("aws_bdd_output_bucket")
AWS_ARCHIVE_BUCKET = os.getenv("aws_bdd_archive_bucket")
AWS_ACCESS_KEY_ID = os.getenv("aws_access_key_id")
AWS_SECRET_ACCESS_KEY = os.getenv("aws_secret_access_key")
AWS_LOB_FILES = os.getenv("aws_lob_files")
AWS_TEST_OUTPUT_BUCKET = os.getenv("aws_test_output_bucket")
AWS_GUNIT_BUCKET = os.getenv("aws_gunit_bucket")

# openai.api_key = OPENAI_API_KEY

safety_settings = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE"
    },
]

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)


def upload_file_to_s3(username):
    try:
        file = f"./static/uploads/{username}_input.xlsx"
        s3_client.upload_file(file, AWS_BDD_INPUT_BUCKET, f'{username}_input.xlsx')
        return True
    except Exception as e:
        print(e)
        return False


def generate_openai_response(prompt):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo-16k",
        messages=[{"role": "user", "content": prompt}],
        temperature=1,
        max_tokens=15000,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    return response.choices[0].message.content


def generate_bdd_from_jira(user_story):
    responses = []
    for story in user_story:
        response = generate_openai_response("Generate BDD scenario in feature file format for the user story " + story)
        responses.append([story, response])
    df1 = pd.DataFrame(responses)
    with io.StringIO() as csv_buffer:
        df1.to_csv(csv_buffer, index=False)
        ts = str(int(round(time.time())))
        response = s3_client.put_object(
            Bucket=AWS_BDD_OUTPUT_BUCKET, Key=f"output_{ts}.csv", Body=csv_buffer.getvalue()
        )
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        url = f"https://{AWS_BDD_OUTPUT_BUCKET}.s3.amazonaws.com/output_{ts}.csv"
        if status == 200:
            return url
        else:
            return None


def generate_bdd_scenario(username):
    s3_client_data = s3_client.get_object(Bucket=AWS_BDD_INPUT_BUCKET, Key=f'{username}_input.xlsx')
    contents = s3_client_data['Body'].read()  # your Excel's essence, pretty much a stream
    # Read in data_only mode to parse Excel after all formulae evaluated
    wb = load_workbook(filename=(io.BytesIO(contents)), data_only=True)
    sheet = wb.active
    responses = []
    for row in range(2, sheet.max_row + 1):
        prompt = sheet.cell(row, 1).value
        response = generate_openai_response("Generate BDD scenario in feature file format for the user story " + prompt)
        responses.append(response)
    df1 = pd.DataFrame(responses)
    with io.StringIO() as csv_buffer:
        df1.to_csv(csv_buffer, index=False)
        ts = str(int(round(time.time())))
        response = s3_client.put_object(
            Bucket=AWS_BDD_OUTPUT_BUCKET, Key=f"output_{ts}.csv", Body=csv_buffer.getvalue()
        )
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        s3 = boto3.resource('s3')
        s3.Object(AWS_ARCHIVE_BUCKET, f'{username}_input_{ts}.xlsx').copy_from(
            CopySource=f'{AWS_BDD_INPUT_BUCKET}/{username}_input.xlsx')
        s3.Object(AWS_BDD_INPUT_BUCKET, f'{username}_input.xlsx').delete()
        url = f"https://{AWS_BDD_OUTPUT_BUCKET}.s3.amazonaws.com/output_{ts}.csv"
        if status == 200:
            return url
        else:
            return None


def generate_test_data(lob, state, no_of_test_cases):
    s3_client_data = s3_client.get_object(Bucket=AWS_LOB_FILES, Key=f'{lob}.txt')
    contents = s3_client_data['Body'].read()  # Reading the txt file
    responses = []
    round_of_test_data = int(no_of_test_cases) // 10
    for test_cases_no in range(round_of_test_data + 1):
        prompt = (f"Generate 10 test data for a {lob} policy according to the following criteria:\n"
                  f"include state {state} and {lob} for the line of business  using the following data\n"
                  + contents.decode('utf-8') + "\n in a csv format only.")
        response = generate_openai_response(prompt)
        if test_cases_no == 0:
            responses.append(response)
        else:
            response_text = "\n".join(response.split("\n")[1:])
            responses.append(response_text)
    responses_bytes = ("\n".join(responses)).encode('utf-8')
    ts = str(int(round(time.time())))
    response = s3_client.put_object(
        Bucket=AWS_TEST_OUTPUT_BUCKET, Key=f"{lob}_{ts}.csv", Body=responses_bytes
    )
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    url = f"https://{AWS_TEST_OUTPUT_BUCKET}.s3.amazonaws.com/{lob}_{ts}.csv"
    if status == 200:
        return url
    else:
        return None


def generate_gunit_data(lob, builder, base_method, features):
    s3_client_data = s3_client.get_object(Bucket=AWS_GUNIT_BUCKET, Key=f'entityTableDescriptions.txt')
    contents = s3_client_data['Body'].read().decode('utf-8')
    s3_client_data = s3_client.get_object(Bucket=AWS_GUNIT_BUCKET, Key=f'DataBuilderFormat.txt')
    data_builder = s3_client_data['Body'].read().decode('utf-8')
    s3_client_data = s3_client.get_object(Bucket=AWS_GUNIT_BUCKET, Key=f'GunitFormat.txt')
    gunit_format = s3_client_data['Body'].read().decode('utf-8')
    s3_client_data = s3_client.get_object(Bucket=AWS_GUNIT_BUCKET, Key=f'DataGeneratorFormat.txt')
    data_generator = s3_client_data['Body'].read().decode('utf-8')

    target_entity = ('cc_' + builder)
    pattern = r'\b' + re.escape(target_entity) + r'\.(\w+)\b'

    columns = re.findall(pattern, contents)
    print(f"Columns: {', '.join(columns)}")

    data_builder_prompt = (
        f"{data_builder} here is an basic structure of what a builder class looks like in guidewire which uses gosu "
        f"based on this can"
        f"you create a {builder} builder for {lob} line of business which has the objects {features}"
        f"and the {builder} entity has following columns {columns}  I want you to go throught all the coulumns and "
        f"chose the most appropriate ones which are related to this builder and generate a builder method for "
        f"guidewire in gosu only generate the code no extra text"
    )
    print("data_builder:", data_builder_prompt)

    data_builder_output = generate_openai_response(data_builder_prompt)

    data_generator_prompt = (
        f"{data_builder_output} using the methods builder can you set the properties of a {builder} and put that into "
        f"a function  for guidewire in gosu only generate the code no extra text.The basic structure of a data "
        f"generator in guidewire is {data_generator} based on this structure create a data generator for {builder} add the "
        f"necessary objects required for a {builder}"
    )
    data_generator_output = generate_openai_response(data_generator_prompt)
    gunit_generation_prompt = (
        f"{gunit_format} here is what a gunit looks like guidewire in gosu.Now can you create a gunit for this base "
        f"method{base_method} and call this data generator function {data_generator_output} to get test data for this "
        f"gunit  in guidewire in gosu only generate the code no extra text"
    )

    gunit_generation_output = generate_openai_response(gunit_generation_prompt)
    print("data_builder:\n:", data_builder_output)
    print("data generator:\n", data_generator_output, "\n")
    print("gunit:\n", gunit_generation_output, "\n")
    return data_generator_output, gunit_generation_output
