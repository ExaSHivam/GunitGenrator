import io
import os
from typing import List

import anthropic
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
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name="us-east-1"

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
    if isinstance(response, str):
        code_start = response.find("```")
        code_end = response.rfind("```")
        if code_start != -1 and code_end != -1:
            return response[code_start + 3: code_end].strip()
        return response
    elif hasattr(response, 'text'):
        response_text = response.text
        code_start = response_text.find("```")
        code_end = response_text.rfind("```")
        if code_start != -1 and code_end != -1:
            return response_text[code_start + 3: code_end].strip()
        return response_text
    elif isinstance(response, list) or hasattr(response, '__iter__'):
        for item in response:
            if hasattr(item, 'text'):
                item_text = item.text
                code_start = item_text.find("```")
                code_end = item_text.rfind("```")
                if code_start != -1 and code_end != -1:
                    return item_text[code_start + 3: code_end].strip()
    else:
        raise ValueError("Invalid input type for extract_code function")


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
            match = re.match(r'(\w+)\s+([\w\.]+)', text)
            if match:
                field_name = match.group(1)
                field_type = match.group(2)
                field_map[field_name] = field_type
                print(f"Matched general field: {field_name} -> {field_type}")
            type_key_match = re.search(r'(\w+)\s+type key to (\w+)', text)
            if type_key_match:
                field_name = type_key_match.group(1)
                field_type = f"typekey.{type_key_match.group(2)}"
                field_map[field_name] = field_type
                # Check for array key pattern
            array_key_match = re.search(r'(\w+)\s+array key for (\w+)', text)
            if array_key_match:
                field_name = array_key_match.group(1)
                field_type = f"ArrayList<{array_key_match.group(2)}>"
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

    data_type_mapping_template = get_excel_from_s3('DatatypeMapping.xlsx')
    print("Excel Data:\n", data_type_mapping_template)
    updated_column_type_map = replace_column_types(column_type_map, data_type_mapping_template)
    print("Updated Column Type Map:", updated_column_type_map)
    object_data = get_excel_from_s3('Test_Data_GENAI.xlsx')
    base_method = extract_base_method_function(all_base_methods, base_method_name)
    print("Base Methods:", base_method)
    fields_to_exclude = "createtime, createuser, updatetime, updateuser, ID, publicID, retiredValue,policySystemAdd"

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
                    f"type of it inside the methods accordingly and also exclude this fields if there {fields_to_exclude}. Generate only the "
                    f"code, no extra text."
                )
                print("data builder prompt", data_builder_prompt)
                data_builder_response = generate_openai_response(data_builder_prompt)
                data_builder_output = extract_code(data_builder_response)
            else:
                data_builder_prompt = (
                    f"{data_builder_output} Here is a data builder. Generate only the methods for these columns {chunk_str}, "
                    f"similar to the methods inside the provided data builder and also exclude this fields if there "
                    f"{fields_to_exclude}. Generate only the code, no extra text."
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
        f"for {builder} and the data to add for each field should be taken from here {object_data} read the comments "
        f"in the example i provided and make sure to follow them"
    )
    data_generator_response = generate_openai_response(data_generator_prompt)
    data_generator_output = extract_code(data_generator_response)

    gunit_generation_prompt = (
        f"{gunit_format} here is what a gunit looks like guidewire in gosu.Now can you create a gunit for this base "
        f"method{base_method} and call this data generator function {data_generator_output} to get test data for this "
        f"gunit and write the methods being used inside the gunit class not in data generator in guidewire in gosu "
        f"only generate the code no extra text. Please try to use the imports for the generated builder in this session"
    )
    gunit_generation_response = generate_openai_response(gunit_generation_prompt)
    gunit_generation_output = extract_code(gunit_generation_response)
    print("Data Builder:\n", data_builder_output)
    print("Data Generator:\n", data_generator_output, "\n")
    print("GUnit:\n", gunit_generation_output, "\n")
    return data_builder_output, gunit_generation_output
# client = anthropic.Anthropic(
#     # defaults to os.environ.get("ANTHROPIC_API_KEY")
#     api_key=os.getenv('claude_apiKey'),
# )
#
#
# def format_code(response):
#     if isinstance(response, list):
#         code_blocks = []
#         for item in response:
#             if isinstance(item, str):
#                 code_start = item.find("```")
#                 code_end = item.rfind("```")
#                 if code_start != -1 and code_end != -1:
#                     code_blocks.append(item[code_start + 3:code_end].strip())
#             elif hasattr(item, 'text'):
#                 code_start = item.text.find("```")
#                 code_end = item.text.rfind("```")
#                 if code_start != -1 and code_end != -1:
#                     code_blocks.append(item.text[code_start + 3:code_end].strip())
#                 else:
#                     code_blocks.append(item.text.strip())
#
#         if code_blocks:
#             return "\n\n".join(code_blocks)
#         else:
#             return None
#     elif isinstance(response, str):
#         if "```" in response:
#             code_start = response.find("```")
#             code_end = response.rfind("```")
#             return response[code_start + 3:code_end].strip()
#         else:
#             return response.strip()
#     else:
#         raise ValueError("Invalid input type for format_code function")
#
#
# def get_response(prompt):
#     output = client.messages.create(
#         model="claude-3-sonnet-20240229",
#         max_tokens=4000,
#         temperature=0,
#         messages=[{"role": "user", "content": prompt}],
#     )
#     return output.content
#
#
# def generate_gunit_data_claude(lob, builder, base_method_name, features):
#     folder_name = 'full/'
#     builder_name = f'{builder}.html'
#     result = search_builder(folder_name, builder_name)
#     pre_signed_url = result.get('pre_signed_url', '')
#     print("pre_signed_url:", pre_signed_url)
#
#     field_map = extract_data_from_html(pre_signed_url)
#     print("Field Map:", field_map)
#
#     all_base_methods = get_object_from_s3('baseMethods.txt')
#     contents = get_object_from_s3('entityTableDescriptions.txt')
#     data_builder_template = get_object_from_s3('DataBuilderFormat.txt')
#     gunit_format = get_object_from_s3('GunitFormat.txt')
#     data_generator_template = get_object_from_s3('DataGeneratorFormat.txt')
#     builder = builder.lower()
#     target_entity = 'cc_' + builder
#     pattern = rf'\b{re.escape(target_entity)}\.(\w+)\b'
#     columns = re.findall(pattern, contents)
#     print("Columns:", columns)
#
#     column_type_map = {col: field_map.get(col, 'unknown') for col in columns if
#                        field_map.get(col) != 'softentityreference'}
#     print("Column Type Map:", column_type_map)
#
#     data_type_mapping_template = get_excel_from_s3('DatatypeMapping.xlsx')
#     print("Excel Data:\n", data_type_mapping_template)
#     updated_column_type_map = replace_column_types(column_type_map, data_type_mapping_template)
#     print("Updated Column Type Map:", updated_column_type_map)
#     object_data = get_excel_from_s3('Test_Data_GENAI.xlsx')
#     base_method = extract_base_method_function(all_base_methods, base_method_name)
#     print("Base Methods:", base_method)
#     fields_to_exclude = "createtime, createuser, updatetime, updateuser, ID, publicID, retiredValue,policySystemAdd"
#
#     find_builder = get_object_from_s3(f'{builder}Builder.txt')
#
#     chunk_size = 25
#     count2 = 0
#     data_builder_output = ""  # Initialize data_builder_output as an empty string
#     combined_code = ""
#     if not find_builder:
#         column_chunks = [{k: updated_column_type_map[k] for k in list(updated_column_type_map)[i:i + chunk_size]}
#                          for i in range(0, len(updated_column_type_map), chunk_size)]
#         data_builder_response = ""
#         all_methods = []
#         for count, chunk in enumerate(column_chunks):
#             chunk_str = ', '.join([f'{col}: {typ}' for col, typ in chunk.items()])
#             if count == 0:
#                 data_builder_prompt = (
#                     f"{data_builder_template} Here is a basic structure of a data builder class in Guidewire using Gosu. "
#                     f"Based on this, create a data builder for the {lob} line of business with the objects {features}. "
#                     f"The {builder} entity has the following columns: {chunk_str}.i want you to create a data based "
#                     f"on the data i provided and also exclude this fields if there {fields_to_exclude}."
#                     f"Generate only the code for {builder}, no extra text i only want the builder code just like i "
#                     f"provided don add how to use the builders inside the builder."
#                 )
#                 print("data builder prompt", data_builder_prompt)
#                 data_builder_response = get_response(data_builder_prompt)
#                 print("data builder response:",data_builder_response)
#                 data_builder_output = format_code(data_builder_response)
#                 print("data builder output:", data_builder_output)
#                 count = count + 1
#             else:
#                 count2 = 1
#                 data_builder_prompt = (
#                     f"{data_builder_output} Here is a data builder. Generate only the methods and not the class  for "
#                     f"these columns {chunk_str},"
#                     f"similar to the methods inside the provided data builder and also exclude this fields if there "
#                     f"{fields_to_exclude}. Generate only the code, no extra text."
#                 )
#                 data_builder_response = get_response(data_builder_prompt)
#                 print("response:", data_builder_response)
#
#                 # Extract the text from the TextBlock object
#                 response_text = data_builder_response[0].text if data_builder_response else ""
#
#                 new_methods = format_code(response_text)
#                 print("new methods:", new_methods)
#                 if new_methods:
#                     all_methods.extend(new_methods.split('\n'))
#         if count2 == 1:
#             data_builder_output += "\n".join(all_methods)
#             data_builder_output += "\n}"
#
#     else:
#         data_builder_output = find_builder
#
#     data_generator_prompt = (
#         f"{data_builder_response} call the methods inside the builder can you set the properties of a {builder} and  "
#         f"create a data generator for guidewire in gosu only generate the code no extra text.The basic structure of "
#         f"a data generator in guidewire is {data_generator_template} based on this structure create a data generator "
#         f"for {builder} and the data to add for each field should be taken from here {object_data} read the comments "
#         f"in the example i provided and make sure to follow them also add the only the for the fields which "
#         f"has methods in the data builder and remove the data which doesn't have methods"
#     )
#     data_generator_response = get_response(data_generator_prompt)
#     print("data generator:", data_generator_response)
#
#     data_generator_output = format_code(data_generator_response)
#
#     gunit_generation_prompt = (
#         f"{gunit_format} here is what a gunit looks like guidewire in gosu.Now can you create a gunit for this base "
#         f"method{base_method} and call this data generator function {data_generator_response} to get test data for this "
#         f"gunit also keep in mind its just an example and there are no helper or util classes available so do "
#         f"everything inside the same class as the gunit and extract the whole data generator function from data "
#         f"generator and put it in the gunit class and use those methods to create the gunit and in then part test "
#         f"both positive and negative scenario and also create the methods needed for the gunit and the imports required "
#         f"should be created according to the comments provided in the reference.Generate this in gosu"
#     )
#     gunit_generation_response = get_response(gunit_generation_prompt)
#     gunit_generation_output = format_code(gunit_generation_response)
#     print("Data Builder:\n", data_builder_output)
#     print("Data Generator:\n", data_generator_output, "\n")
#     print("GUnit:\n", gunit_generation_output, "\n")
#     return data_builder_output, gunit_generation_output
