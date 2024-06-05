import os


from flask import Flask, render_template, request, redirect, session, jsonify
from aws_s3 import generate_gunit_data_claude
from llama_claude import generate_gunit_data_llama

# from claude_ai import generate_gunit_data_claude, generate_gunit_data_claude_llama

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_FOLDER = './static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


@app.route("/")
def home():
    return render_template('index.html')


@app.route("/generate_gunit", methods=['POST'])
def generate_gunit():

    selected_lob = request.form.get('selected_lob')
    builder = request.form.get('builder')
    # print("builder", builder)
    base_method = request.form.get('base_method')
    print("base method", base_method)
    features = request.form.getlist("features")
    # print("objects", features)

    response, response1 = generate_gunit_data_claude(selected_lob, builder, base_method, features)
    # print("Data Builder: ", response)
    # print("Gunit: ", response1)

    return render_template('index.html',
                           status="Gunit Successfully Generated",
                           response=response,
                           response1=response1,
                           selected_lob=selected_lob,
                           builder=builder)

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
