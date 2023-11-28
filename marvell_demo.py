import os
from langchain.prompts import PromptTemplate
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.prompts.few_shot import FewShotPromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.vectorstores import FAISS
from langchain.prompts.example_selector import SemanticSimilarityExampleSelector
import openai
from logging import exception
import snowflake.connector
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
from tabulate import tabulate
from PIL import Image

from io import StringIO
from langchain.chains import RetrievalQA
from FewShotSettings import few_shot_settings


class few_shot_prompt_utility:

    def __init__(self, examples, prefix, suffix, input_variables, example_template, example_variables):
        self.examples = examples
        self.prefix = prefix
        self.suffix = suffix
        self.input_variables = input_variables
        self.example_template = example_template
        self.example_variables = example_variables

    def get_prompt_template(self):
        example_prompt = PromptTemplate(
            input_variables=self.example_variables,
            template=self.example_template
        )
        return example_prompt
    
    def get_embeddings(self):
        embeddings = OpenAIEmbeddings(openai_api_key= st.secrets["openai_key"])
        return embeddings
    
    def get_example_selector(self, embeddings):
        example_selector = SemanticSimilarityExampleSelector.from_examples(
            self.examples,
            embeddings,
            FAISS,
            k=3
        )
        return example_selector
        
    def get_prompt(self, question, example_selector, example_prompt):
        prompt_template = FewShotPromptTemplate(
            example_selector=example_selector,
            example_prompt=example_prompt,
            prefix=self.prefix,
            suffix=self.suffix,
            input_variables=self.input_variables
        )
        prompt = prompt_template.format(question=question, context="Inventory")
        return prompt_template
		

llm = ChatOpenAI(
    model_name="gpt-3.5-turbo",
    temperature=0.1,
    max_tokens=1000,
    openai_api_key="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"
)

prefix = few_shot_settings.get_prefix()
suffix, input_variable = few_shot_settings.get_suffix()
examples = few_shot_settings.get_examples()
example_template, example_variables = few_shot_settings.get_example_template()
fewShot = few_shot_prompt_utility(examples=examples,
                                        prefix=prefix,
                                        suffix=suffix,
                                        input_variables=input_variable,
                                        example_template=example_template,
                                        example_variables=example_variables
                                        )


def fs_chain(question):
  """
    returns a question answer chain for faiss vectordb
  """
  example_prompt = fewShot.get_prompt_template()
  embeddings = fewShot.get_embeddings()
  example_selector = fewShot.get_example_selector(embeddings)
  prompt_template = fewShot.get_prompt(question, example_selector, example_prompt)
  docsearch = FAISS.load_local("faiss_index", embeddings)
  qa_chain = RetrievalQA.from_chain_type(llm, retriever=docsearch.as_retriever(), chain_type_kwargs={"prompt": prompt_template})
  return qa_chain({"query": question})

st.set_page_config(layout="wide")

username=st.secrets["streamlit_username"]
password=st.secrets["streamlit_password"]
column_list = ["AMOUNT"]
cutoff = 20
# establish snowpark connection
conn = st.connection("snowpark")

# Reset the connection before using it if it isn't healthy
try:
    query_test = conn.query('select 1')
except:
    conn.reset()

# adding this to test out caching
st.cache_data(ttl=86400)

def plot_financials(df_2, x, y, x_cutoff, title):
    """"
    helper to plot the altair financial charts
    
    return st.altair_chart(alt.Chart(df_2.head(x_cutoff)).mark_bar().encode(
        x=x,
        y=y
        ).properties(title=title)
    ) 
    """
    #df_subset = df_2.head(x_cutoff)
    df = pd.DataFrame(df_2)
    return st.bar_chart(data=df,x=df.columns[0], y=df.columns[1:], color=None,width=0, height=300, use_container_width=True)

# adding this to test out caching
st.cache_data(ttl=86400)
def sf_query(str_input):
    """
    performs snowflake query with caching
    """
    data = conn.query(str_input)
    return data

def creds_entered():
    if len(st.session_state["streamlit_username"])>0 and len(st.session_state["streamlit_password"])>0:
          if  st.session_state["streamlit_username"].strip() != username or st.session_state["streamlit_password"].strip() != password: 
              st.session_state["authenticated"] = False
              st.error("Invalid Username/Password ")

          elif st.session_state["streamlit_username"].strip() == username and st.session_state["streamlit_password"].strip() == password:
              st.session_state["authenticated"] = True


def authenticate_user():
      if "authenticated" not in st.session_state:
        buff, col, buff2 = st.columns([1,1,1])
        col.text_input(label="Username:", value="", key="streamlit_username", on_change=creds_entered) 
        col.text_input(label="Password", value="", key="streamlit_password", type="password", on_change=creds_entered)
        return False
      else:
           if st.session_state["authenticated"]: 
                return True
           else:  
                  buff, col, buff2 = st.columns([1,1,1])
                  col.text_input(label="Username:", value="", key="streamlit_username", on_change=creds_entered) 
                  col.text_input(label="Password:", value="", key="streamlit_password", type="password", on_change=creds_entered)
                  return False

if authenticate_user():
    with st.sidebar:
      image = Image.open("assets/jadenew.png")
      image = st.image('assets/jadenew.png',width=280)
      
    str_input = st.chat_input("Enter your question:")
    st.markdown("""
    I am  Finance Assistant of your company. I possess the ability to extract information from your company's financial statements like balance sheet, income statements, etc spanning across 2003 to 2022. Please ask me questions and I will try my level best to provide accurate responses.
      
  
      **Some Sample Questions:**
  
      - What was the total Ending Gross Inventory dollar amount at the end of last quarter?
      - What is the projected inventory for all the parts in BBA BU per quarter?
      - How many 5nm parts are available and in what BU?
      - What is the Inventory on hand for 5nm parts in 2024-Q4 and what is the average yield quantity?
    
    
    """)
    
    if "messages" not in st.session_state.keys():
          st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            role = message["role"]
            df_str = message["content"]
            if role == "user":
                st.markdown(message["content"], unsafe_allow_html = True)
                continue
            csv = StringIO(df_str)
            df_data = pd.read_csv(csv, sep=',')
            col1, col2 = st.columns(2)
            df_data.columns = df_data.columns.str.replace('_', ' ')
            headers = df_data.columns
            
            with col1:
                st.markdown(tabulate(df_data, tablefmt="html",headers=headers,showindex=False), unsafe_allow_html = True) 
                if len(df_data.index) >2 & len(df_data.columns) == 2:
                    title_name = df_data.columns[0]+'-'+df_data.columns[1]
                    with col2:
                            grph_ser_val_x1  = df_data.iloc[:,0]
                            grph_ser_val_y1  = df_data.iloc[:,1].apply(lambda x : float(str(x).replace(',','')))
                            frame = {df_data.columns[0] : grph_ser_val_x1,
                                     df_data.columns[1] : grph_ser_val_y1}
                            df_final1 = pd.DataFrame(frame)
                            plot_financials(df_final1,df_data.columns[0],df_data.columns[1], cutoff,title_name)
    
    if prompt := str_input:
        st.chat_message("user").markdown(prompt, unsafe_allow_html = True)
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})

        try:
            #st.write(str_input)
            output = fs_chain(str_input)
            #st.write(output)
            #st.write(output['result'])
            try:
                # if the output doesn't work we will try one additional attempt to fix it
                query_result = sf_query(output['result'])
                if len(query_result) >= 1:
                  with st.chat_message("assistant"):
                    df_2 = pd.DataFrame(query_result)
                    for name in df_2.columns:
                        if name in column_list:
                            new_name = f"{name} ($ thousands)"
                            df_2.rename(columns={name : new_name}, inplace=True)
                    
                    col1, col2 = st.columns(2)
                    df_2.columns = df_2.columns.str.replace('_', ' ')
                    headers = df_2.columns
                    with col1:
                     st.markdown(tabulate(df_2, tablefmt="html",headers=headers,showindex=False), unsafe_allow_html = True) 
                    if len(df_2.index) >2 & len(df_2.columns) == 2:
                        title_name = df_2.columns[0]+'-'+df_2.columns[1]
                        with col2:
                            grph_ser_val_x  = df_2.iloc[:,0]
                            grph_ser_val_y  = df_2.iloc[:,1].apply(lambda x : float(str(x).replace(',','')))
                            frame = {df_2.columns[0] : grph_ser_val_x,
                                     df_2.columns[1] : grph_ser_val_y}
                            df_final = pd.DataFrame(frame)
                            plot_financials(df_final,df_2.columns[0],df_2.columns[1], cutoff,title_name)
                  st.session_state.messages.append({"role": "assistant", "content": df_2.to_csv(sep=',', index=False)})
                    
                else:
                  with st.chat_message("assistant"):
                    st.write("Data for the provided question is not available. Please try to improve your question.")
  
            except Exception as error:
                  st.write(error)                   
                  output = fs_chain(f'You need to fix the code but ONLY produce SQL code output. If the question is complex, consider using one or more CTE. Examine the DDL statements and answer this question: {output}')
                  st.write(sf_query(output['result']))
        except Exception as error:
          st.write(error)       
          with st.chat_message("assistant"):
            st.markdown("Data for the provided question is not available. Please try to improve your question. ")
