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

# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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


# def generate_openai_response(prompt):
#     response = client.chat.completions.create(
#         model=os.getenv("openAI_model"),
#         messages=[{"role": "user", "content": prompt}],
#         temperature=0,
#         max_tokens=7000,
#         top_p=1,
#         frequency_penalty=0,
#         presence_penalty=0
#     )
#     return response.choices[0].message.content

def get_excel_from_s3(object_name):
    try:
        s3_client_data = s3_client.get_object(Bucket=AWS_GUNIT_BUCKET, Key=object_name)
        raw_data = s3_client_data['Body'].read()

        # Print raw data for debugging
        print("Raw Data:", raw_data[:100])  # Print first 100 bytes for inspection

        excel_data = pd.read_excel(io.BytesIO(raw_data), engine='openpyxl')

        # Strip and replace non-breaking spaces from column names
        print("excel_data",excel_data)
        return excel_data
    except s3_client.exceptions.NoSuchKey:
        return None


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
                print("file to search", file_to_search)
                print("Checking Key:", obj['Key'])
                print("obejectKey:", obj['Key'])
                if obj['Key']==(folder_name+file_to_search):
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
            foriegn_key_match = re.search(r'(\w+)\s+foreign key to (\w+)', text)
            if foriegn_key_match:
                field_name = foriegn_key_match.group(1)
                field_type = f"{foriegn_key_match.group(2)}"
                field_map[field_name] = field_type

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


# def generate_gunit_data(lob, builder, base_method_name, features):
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
#     data_builder_output = ""
#
#     if not find_builder:
#         column_chunks = [{k: updated_column_type_map[k] for k in list(updated_column_type_map)[i:i + chunk_size]}
#                          for i in range(0, len(updated_column_type_map), chunk_size)]
#         all_methods = []
#         for count, chunk in enumerate(column_chunks):
#             chunk_str = ', '.join([f'{col}: {typ}' for col, typ in chunk.items()])
#             if count == 0:
#                 data_builder_prompt = (
#                     f"{data_builder_template} Here is a basic structure of a builder class in Guidewire using Gosu. "
#                     f"Based on this, create a {builder} builder for the {lob} line of business with the objects {features}. "
#                     f"The {builder} entity has the following columns: {chunk_str}.exclude this fields if there {fields_to_exclude}. Generate only the "
#                     f"code, no extra text.Keep the name of the type of the columns exactly same as the type I am providing"
#                 )
#                 print("data builder prompt", data_builder_prompt)
#                 data_builder_response = generate_openai_response(data_builder_prompt)
#                 data_builder_output = extract_code(data_builder_response)
#             else:
#                 data_builder_prompt = (
#                     f"{data_builder_output} Here is a data builder. Generate only the methods for these columns {chunk_str}, "
#                     f"similar to the methods inside the provided data builder,don't add the code for the class and "
#                     f"also check if this fields are there"
#                     f"{fields_to_exclude} and don't add them in the code. Generate only the code, no extra text."
#                     f"Keep the name of the type of the columns exactly same as the type I am providing"
#                 )
#                 data_builder_response = generate_openai_response(data_builder_prompt)
#                 all_methods.extend(extract_code(data_builder_response).split('\n'))
#
#         data_builder_output += "\n".join(all_methods)
#         data_builder_output += "\n}"
#     else:
#         data_builder_output = find_builder
#
#     data_generator_prompt = (
#         f"{data_builder_output} call the methods inside the builder can you set the properties of a {builder} and  "
#         f"create a data generator for guidewire in gosu only generate the code no extra text.The basic structure of "
#         f"a data generator in guidewire is {data_generator_template} based on this structure create a data generator "
#         f"for {builder} and the data to add for each field should be taken from here {object_data} read the comments "
#         f"in the example i provided and make sure to follow them"
#     )
#     data_generator_response = generate_openai_response(data_generator_prompt)
#     data_generator_output = extract_code(data_generator_response)
#
#     gunit_generation_prompt = (
#         f"{gunit_format} here is what a gunit looks like guidewire in gosu.Now can you create a gunit for this base "
#         f"method{base_method_name} and call this data generator function {data_generator_output} to get test data for this "
#         f"gunit and write the methods being used inside the gunit class not in data generator in guidewire in gosu "
#         f"only generate the code no extra text. Please try to use the imports for the generated builder in this session"
#     )
#     gunit_generation_response = generate_openai_response(gunit_generation_prompt)
#     gunit_generation_output = extract_code(gunit_generation_response)
#     print("Data Builder:\n", data_builder_output)
#     print("Data Generator:\n", data_generator_output, "\n")
#     print("GUnit:\n", gunit_generation_output, "\n")
#     return data_builder_output, gunit_generation_output
client = anthropic.Anthropic(
    # defaults to os.environ.get("ANTHROPIC_API_KEY")
    api_key=os.getenv('claude_apiKey'),
)


def format_code(response):
    if isinstance(response, list):
        code_blocks = []
        for item in response:
            if isinstance(item, str):
                code_start = item.find("```")
                code_end = item.rfind("```")
                if code_start != -1 and code_end != -1:
                    code_blocks.append(extract_code(item))
            elif hasattr(item, 'text'):
                code_start = item.text.find("```")
                code_end = item.text.rfind("```")
                if code_start != -1 and code_end != -1:
                    code_blocks.append(extract_code(item.text))
                else:
                    code_blocks.append(item.text.strip())

        code_blocks = [block for block in code_blocks if block]
        return "\n\n".join(code_blocks) if code_blocks else None

    elif isinstance(response, str):
        code_start = response.find("```")
        code_end = response.rfind("```")
        if code_start != -1 and code_end != -1:
            return extract_code(response)
        else:
            return response.strip()

    else:
        raise ValueError("Invalid input type for format_code function")


def get_response(prompt):
    output = client.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=4000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return output.content


def generate_gunit_data_claude(lob, builder, base_method_name, features):
    folder_name = 'full/'
    builder_name = f'{builder}.html'
    builder_name_ootd = f'{builder}Builder'
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
    ootb_builder_check = get_excel_from_s3('list_of_builders.xlsx')

    is_present = builder_name_ootd in ootb_builder_check['List of ootb builder'].values
    print(is_present)

    print(ootb_builder_check)

    if is_present:
        data_builder_template = get_object_from_s3('custom_Data_Builder.txt')
        print("Custom builder:",data_builder_template)
        pattern_ext = rf'\b{re.escape(target_entity)}\.(\w+_Ext)\b'
        columns = re.findall(pattern_ext, contents)
        print("Columns with target entity and ending with '_Ext':", columns)
    else:
        pattern = rf'\b{re.escape(target_entity)}\.(\w+)\b'
        columns = re.findall(pattern, contents)
        print("Columns:", columns)

    column_type_map = {col: field_map.get(col, 'unknown') for col in columns if field_map.get(col) != 'softentityreference'}
    print("Column Type Map:", column_type_map)

    data_type_mapping_template = get_excel_from_s3('dataTypeMapping.xlsx')
    print("Excel Data:\n", data_type_mapping_template)
    updated_column_type_map = replace_column_types(column_type_map, data_type_mapping_template)
    print("Updated Column Type Map:", updated_column_type_map)
    object_data = get_excel_from_s3(f'{builder}Data.xlsx')
    print("object_data", object_data.to_string())
    object_data = object_data.to_string()
    base_method = extract_base_method_function(all_base_methods, base_method_name)
    print("Base Methods:", base_method_name)
    fields_to_exclude = "createtime, createuser, updatetime, updateuser, ID, publicID, retiredValue,policySystemAdd"

    find_builder = get_object_from_s3(f'{builder}Builder.txt')
    print("find builder:", find_builder)

    chunk_size = 25
    count2 = 0
    data_builder_output = ""  # Initialize data_builder_output as an empty string
    combined_code = ""
    if find_builder is None:
        column_chunks = [{k: updated_column_type_map[k] for k in list(updated_column_type_map)[i:i + chunk_size]}
                         for i in range(0, len(updated_column_type_map), chunk_size)]
        data_builder_response = ""
        all_methods = []
        for count, chunk in enumerate(column_chunks):
            chunk_str = ', '.join([f'{col}: {typ}' for col, typ in chunk.items()])
            if count == 0:
                data_builder_prompt = (
                    f"{data_builder_template} Here is a basic structure of a data builder class in Guidewire using Gosu. "
                    f"Based on this, create a data builder for the {lob} line of business with the objects {features} added to the builder. "
                    f"The {builder} entity has the following columns: {chunk_str},generate only the methods for the fields in the chunk and objects if provided by me they should be similar to the methods of the columns I want you to create a data based "
                    f"on the data I provided and also exclude these fields if they exist: {fields_to_exclude}. "
                    f"Generate only the code for {builder}, no extra text. I only want the builder code just like the reference I "
                    f"provided. Do not add how to use the builders inside the builder. Add all the uses and imports from the reference I am providing. Keep the data types of the fields exactly the same."
                )
                print("data builder prompt:", data_builder_prompt)
                data_builder_response = get_response(data_builder_prompt)
                print("data builder response:", data_builder_response)
                data_builder_output = format_code(data_builder_response)
                print("data builder output:", data_builder_output)

                count = count + 1
            else:
                count2 = 1
                data_builder_prompt = (
                    f"{data_builder_output} Here is a data builder. Generate only the methods and not the class for "
                    f"these columns {chunk_str}, similar to the methods inside the provided data builder. Exclude these fields if they exist: "
                    f"{fields_to_exclude}. Generate only the code, no extra text. Keep the data types of the fields exactly the same."
                )
                data_builder_response = get_response(data_builder_prompt)
                print("response:", data_builder_response)

                # Extract the text from the TextBlock object
                response_text = data_builder_response[0].text if data_builder_response else ""

                new_methods = format_code(response_text)
                print("new methods:", new_methods)
                if new_methods:
                    all_methods.extend(new_methods.split('\n'))
        if count2 == 1:
            data_builder_output += "\n".join(all_methods)
            data_builder_output += "\n}"

    else:
        data_builder_output = find_builder

    data_generator_prompt = (
        f"{data_builder_output} Call the methods inside the builder. Can you set the properties of a {builder} and  "
        f"create a data generator for Guidewire in Gosu? Only generate the code, no extra text. The basic structure of "
        f"a data generator in Guidewire is {data_generator_template}. Based on this structure, create a data generator "
        f"along with these features: {features} only. "
        f"For {builder}, the data to add for each field should be taken from here: {object_data} strictly follow it. The object data "
        f"and the fields which don't have a value here should be set yourself following the trend of the data I provided. "
        f"Set the fields according to the field name beside it and read the comments in the example I provided. Make sure to follow them. Also, add data for all the fields which "
        f"have methods in the data builder, and for nested builders, do it accordingly. Remove the data which doesn't "
        f"have methods. When returning the value, use the .create() method only."
    )
    print("data_generator_prompt",data_generator_prompt)
    data_generator_response = get_response(data_generator_prompt)
    print("data generator:", data_generator_response)

    data_generator_output = format_code(data_generator_response)

    gunit_generation_prompt = (
        f"{gunit_format} Here is what a gunit looks like in Guidewire using Gosu. Now can you create a gunit for this base "
        f"method {base_method_name} and call this data generator function {data_generator_response} to get test data for this "
        f"gunit? Also, keep in mind it's just an example, and there are no helper or util classes available. Do "
        f"everything inside the same class as the gunit and extract the whole data generator function from the data "
        f"generator and put it in the gunit class. Use those methods to create the gunit. "
        "Also, create the methods needed for the gunit and all the imports and uses required "
        f"according to the comments provided in the reference. Generate this in Gosu and only create "
        f"a single method."
    )
    gunit_generation_response = get_response(gunit_generation_prompt)
    print("gunit response:", gunit_generation_response)
    gunit_generation_output = format_code(gunit_generation_response)
    print("Data Builder:\n", data_builder_output)
    print("Data Generator:\n", data_generator_output, "\n")
    print("GUnit:\n", gunit_generation_output, "\n")
    return data_builder_output, gunit_generation_output
