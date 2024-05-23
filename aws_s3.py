import io
import os
import boto3
import re

from flask import jsonify
from openai import OpenAI
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import pandas as pd

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

AWS_ACCESS_KEY_ID = os.getenv("aws_access_key_id")
AWS_SECRET_ACCESS_KEY = os.getenv("aws_secret_access_key")
AWS_GUNIT_BUCKET = os.getenv("aws_gunit_bucket")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

print(os.getenv("openAI_model"))


def generate_openai_response(prompt):
    response = client.chat.completions.create(
        model=os.getenv("openAI_model"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=7000,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    return response.choices[0].message.content


def get_excel_from_s3(object_name):
    s3_client_data = s3_client.get_object(Bucket=AWS_GUNIT_BUCKET, Key=object_name)

    excel_data = pd.read_excel(io.BytesIO(s3_client_data['Body'].read()), engine='openpyxl')

    return excel_data


def get_object_from_s3(object_name):
    try:
        s3_client_data = s3_client.get_object(Bucket=AWS_GUNIT_BUCKET, Key=object_name)
        return s3_client_data['Body'].read().decode('utf-8')
    except s3_client.exceptions.NoSuchKey:
        return None


def extract_code(response):
    code_start = response.find("```")
    code_end = response.rfind("```")
    if code_start != -1 and code_end != -1:
        return response[code_start + 3: code_end].strip()
    return response


def extract_base_method_function(all_base_methods, base_method):
    pattern = rf'public\s+static\s+function\s+{re.escape(base_method)}\s*\([^\)]*\)\s*\{{.*?\}}'

    match = re.search(pattern, all_base_methods, re.DOTALL)

    if match:
        return match.group(0)
    else:
        return None


def search_builder(folder_name, file_to_search):
    try:
        response = s3_client.list_objects_v2(Bucket=AWS_GUNIT_BUCKET, Prefix=folder_name)

        if 'Contents' in response:
            for obj in response['Contents']:
                # print("Checking Key:", obj['Key'])
                if obj['Key'].endswith(file_to_search):
                    pre_signed_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': AWS_GUNIT_BUCKET, 'Key': obj['Key']},
                        ExpiresIn=3600
                    )
                    return {'file_found': True, 'pre_signed_url': pre_signed_url}

        return {'file_found': False}
    except Exception as e:
        return {'error': str(e)}


def extract_data_from_html(url):
    response = requests.get(url)
    if response.status_code == 200:
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')

        paragraphs = soup.find_all('p')
        field_map = {}

        for p in paragraphs:
            text = p.text.strip()
            match = re.match(r'(\w+)\s+(\w+)\s+', text)
            if match:
                field_name = match.group(1)
                field_type = match.group(2)
                field_map[field_name] = field_type

        return field_map
    else:
        print("Failed to fetch HTML content from the URL")
        return {}


def replace_column_types(column_type_map, excel_data):
    type_mapping = dict(zip(excel_data['Datatype Mapping'], excel_data['Unnamed: 1']))

    updated_column_type_map = {k: type_mapping.get(v, v) for k, v in column_type_map.items()}

    return updated_column_type_map


def generate_gunit_data(lob, builder, base_method_name, features):
    folder_name = 'full/'
    builder_name = f'{builder}.html'
    result = search_builder(folder_name, builder_name)
    pre_signed_url = result.get('pre_signed_url', '')
    print("pre_signed_url:", pre_signed_url)

    field_map = extract_data_from_html(pre_signed_url)
    print("Field Map:", field_map)

    all_base_methods = get_object_from_s3('baseMethods.txt')
    contents = get_object_from_s3('entityTableDescriptions.txt')
    data_builder_template = get_object_from_s3('DataBuilderFormat.txt')
    gunit_format = get_object_from_s3('GunitFormat.txt')
    data_generator_template = get_object_from_s3('DataGeneratorFormat.txt')
    builder = builder.lower()
    target_entity = 'cc_' + builder
    pattern = rf'\b{re.escape(target_entity)}\.(\w+)\b'
    columns = re.findall(pattern, contents)
    print("Columns:", columns)

    column_type_map = {col: field_map.get(col, 'unknown') for col in columns if
                       field_map.get(col) != 'softentityreference'}
    print("Column Type Map:", column_type_map)

    excel_data = get_excel_from_s3('datatypeMapping.xlsx')
    print("Excel Data:\n", excel_data)
    updated_column_type_map = replace_column_types(column_type_map, excel_data)
    print("Updated Column Type Map:", updated_column_type_map)

    base_method = extract_base_method_function(all_base_methods, base_method_name)
    print("Base Methods:", base_method)

    find_builder = get_object_from_s3(f'{builder}Builder.txt')

    chunk_size = 25
    data_builder_output = ""

    if not find_builder:
        column_chunks = [{k: updated_column_type_map[k] for k in list(updated_column_type_map)[i:i + chunk_size]}
                         for i in range(0, len(updated_column_type_map), chunk_size)]
        all_methods = []
        for count, chunk in enumerate(column_chunks):
            chunk_str = ', '.join([f'{col}: {typ}' for col, typ in chunk.items()])
            if count == 0:
                data_builder_prompt = (
                    f"{data_builder_template} Here is a basic structure of a builder class in Guidewire using Gosu. "
                    f"Based on this, create a {builder} builder for the {lob} line of business with the objects {features}. "
                    f"The {builder} entity has the following columns: {chunk_str}. change the column names and the   "
                    f"type of it inside the methods accordingly. Generate only the "
                    f"code, no extra text."
                )
                print("data builder prompt",data_builder_prompt)
                data_builder_response = generate_openai_response(data_builder_prompt)
                data_builder_output = extract_code(data_builder_response)
            else:
                data_builder_prompt = (
                    f"{data_builder_output} Here is a data builder. Generate only the methods for these columns {chunk_str}, "
                    f"similar to the methods inside the provided data builder. Generate only the code, no extra text."
                )
                data_builder_response = generate_openai_response(data_builder_prompt)
                all_methods.extend(extract_code(data_builder_response).split('\n'))

        data_builder_output += "\n".join(all_methods)
        data_builder_output += "\n}"
    else:
        data_builder_output = find_builder

    data_generator_prompt = (
        f"{data_builder_output} call the methods inside the builder can you set the properties of a {builder} and  "
        f"create a data generator for guidewire in gosu only generate the code no extra text.The basic structure of "
        f"a data generator in guidewire is {data_generator_template} based on this structure create a data generator "
        f"for {builder} add the necessary objects required for a {builder}"
    )
    data_generator_response = generate_openai_response(data_generator_prompt)
    data_generator_output = extract_code(data_generator_response)

    gunit_generation_prompt = (
        f"{gunit_format} this is the format of a gunit using this as reference can you create a gunit for this base"
        f"method{base_method} and use this class function {data_generator_output} to get test data for this "
        f"gunit  in guidewire in gosu only generate the code for gunit and no extra text or code"
    )
    gunit_generation_response = generate_openai_response(gunit_generation_prompt)
    gunit_generation_output = extract_code(gunit_generation_response)
    print("Data Builder:\n", data_builder_output)
    print("Data Generator:\n", data_generator_output, "\n")
    print("GUnit:\n", gunit_generation_output, "\n")
    return data_builder_output, gunit_generation_output
