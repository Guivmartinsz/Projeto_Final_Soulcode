# PROJETO FINAL - BANCOS(FINANCEIRO)

## IMPORTANDO BIBLIOTECAS
"""

!pip install -q pyspark

!pip install pymongo[srv]

!pip install -q gcsfs

pip install -q pandera

!pip install -q PyMySql

!pip install skimpy

pip install roman

!pip install https://github.com/ydataai/pandas-profiling/archive/master.zip

import time
from time import time
from datetime import datetime, time
import pymongo 
from pymongo import MongoClient
from google.cloud import storage # Para conexão com a GCloud
import pandas as pd
from urllib.request import urlopen
import json
from pyspark.sql.functions import *
from pyspark.sql.types import *
from pyspark.sql import SparkSession
from pyspark import SparkConf
import os
import gcsfs
import pandera as pa
from google.colab import auth
from skimpy import clean_columns
import roman
import pyspark.sql.functions as F
import altair as alt
from pyspark.sql.window import Window
from pyspark.sql.types import *
from pyspark.sql import Column
import pandas_profiling
from pandas_profiling import ProfileReport
from google.oauth2 import service_account
import plotly.graph_objects as go
import warnings
import numpy as np
import matplotlib.pyplot as plt #visualização e ajuste dos graficos
import seaborn as sns #criar gráficos

"""===================================================================

===================================================================

## ACESSO AO GCLOUD
Rotina para acessar a google cloud de forma segura onde apenas emails autorizados conseguem acessar à bucket
"""

auth.authenticate_user()

# https://cloud.google.com/resource-manager/docs/creating-managing-projects
project_id = 'group-one-pfinal-soulcode'

!gcloud config set project {project_id}

# Faz o download da chave na bucket do Google Cloud Storage.
!gsutil cp gs://group_one_bucket/credentials/group-one-pfinal-soulcode-5116eba95465.json /tmp/key.json

# O resultado para garantir que a transferência funcionou.
!cat /tmp/key.json

os.environ['GOOGLE_APPLICATION_CREDENTIALS']='/tmp/key.json'

# função para  Usar explicitamente as credenciais da conta de serviço especificando a chave privada e para solicitação de API autenticada
def explicit():
    from google.cloud import storage

    storage_client = storage.Client.from_service_account_json(
        "/tmp/key.json")

    buckets = list(storage_client.list_buckets())
    print(buckets)

explicit()

"""## PySpark
conectando ao spark
"""

gcs_conector = r'https://storage.googleapis.com/hadoop-lib/gcs/gcs-connector-hadoop2-latest.jar' #conexão

spark = (SparkSession.builder
        .master("local[*]")
        .appName("projeto-final")
        .config('spark.ui.port', '4050')
        .config('spark.jars', gcs_conector)
        .getOrCreate())

#spark.stop()

spark

"""### Gerando jsons com pyspark"""

#CRIAÇÃO DO ESQUEMA
schema = StructType([ 
   StructField("TipoInstituicao", StringType(), True),
   StructField("CodInst", StringType(), True),
   StructField("AnoMes", StringType(), True),
    StructField("NomeRelatorio", StringType(), True),
    StructField("NumeroRelatorio", StringType(), True),
    StructField("Grupo", StringType(), True),
    StructField("Conta", StringType(), True),
    StructField("NomeColuna", StringType(), True),
    StructField("DescricaoColuna", StringType(), True),
    StructField("Saldo", StringType(), True)])

quadrimestre = pd.date_range(start="2019-03", end="2021-10", freq="3M")  # CRIANDO UMA LISTA COM PERÍODOS DE QUADRIMESTRE
quadrimestre = quadrimestre.strftime("%Y%m") # AJUSTANDO O FORMATO DA DATA
for anomes in quadrimestre: # ROTINA PARA AUTOMATIZAR A LEITURA DO SITE DO BANCO CENTRAL
  json_path = f"https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata/IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)?@AnoMes={anomes}&@TipoInstituicao=2&@Relatorio='10'&$format=json"
  response = urlopen(json_path)
  data = json.loads(response.read())
  rdd = data['value']

  df = spark.createDataFrame(rdd, schema=schema)

  df = df.groupby(col('CodInst'),col('AnoMes')).pivot('NomeColuna').agg(sum(col('Saldo').cast('int')))
  df.show(5)
  df.coalesce(1).write.json(r"gs://group_one_bucket/arquivos_brutos/carteira_credito_bancos/carteira_credito",mode='append') # GRAVANDO E SETANDO PARA QUE TENHA SOMENTE UMA PARTIÇÃO

  time.sleep(5)

"""### Carteira de creditos Bancos"""

cart_creditos = spark.createDataFrame(pd.read_parquet('gs://group_one_bucket/arquivos_brutos/carteira_credito_bancos/carteira_creditos.parquet'))

# RENOMEANDO COLUNAS E TRANSFORMANDO TIPOS

cart_creditos = (cart_creditos.withColumnRenamed('Quantidade de operações ativas','Qtd_de_operacoes_ativas').withColumnRenamed('Quantidade de clientes com operações ativas','Qtd_de_clientes_com_operacoes_ativas')
 .withColumn('Qtd_de_operacoes_ativas',col('Qtd_de_operacoes_ativas').cast('int'))
 .withColumn('Qtd_de_clientes_com_operacoes_ativas', col('Qtd_de_clientes_com_operacoes_ativas').cast('int'))
 .withColumn('AnoMes', last_day(to_date(col('AnoMes').cast('string'),format='yyyyMM')))
 .withColumnRenamed('AnoMes','Periodo')
 )

cart_creditos.printSchema()

cart_creditos.select([count(when(col(c).isNull(), c)).alias(c) for c in cart_creditos.columns]).show() # VERIFICANDO NULOS

cart_creditos.summary('count').show() # VERIFICANDO LINHAS NÃO NULAS POR COLUNA

cart_creditos = cart_creditos.filter('Qtd_de_clientes_com_operacoes_ativas IS NOT null OR Qtd_de_operacoes_ativas IS NOT NULL') # LIMPEZA DOS NULOS

cart_creditos = cart_creditos.filter('Qtd_de_clientes_com_operacoes_ativas <> 0 and Qtd_de_operacoes_ativas <> 0') # RETIRANDO CLIENTES E OPERAÇÕES ZERADAS

cart_creditos = cart_creditos.filter('NomeInstituicao IS NOT NULL') # LIMPANDO NULOS

cart_creditos.select([count(when(col(c).isNull(), c)).alias(c) for c in cart_creditos.columns]).show()

cart_creditos.sort(col('Qtd_de_clientes_com_operacoes_ativas').desc()).show()

cart_creditos.coalesce(1).write.parquet('gs://group_one_bucket/arquivos_tratados/carteira_credito/carteira_pd.parquet')

"""###**Resumo_Tratado_SQL_PY**"""

spark = (                                       # CRIANDO A SESSÃO SPARK
    SparkSession.builder
                .master("local[*]")
                .appName("prj_final")
                .config("spark.ui.port", "4050")
                .config("spark.jars", 'https://storage.googleapis.com/hadoop-lib/gcs/gcs-connector-hadoop3-latest.jar')
                .getOrCreate()
)

spark # VERIFICANDO  A SESSÃO E A VERSÃO

#Juntando datasets
folder_path = r"gs://group_one_bucket/arquivos_brutos/InstituicoesFinanceiras_TOT/"
file_list = gcsfs.GCSFileSystem(token=serviceAccount).glob(folder_path + "*.json")
file_list = [os.path.join(r"gs://" + _) for _ in file_list]

df_dr = (pd.concat((pd.read_json(f,lines=True) for f in file_list)))

df_spk = spark.read.parquet("gs://group_one_bucket/arquivos_tratados/Inst_Fin_Resumo")

df_spk.printSchema()

df_spk.dtypes # verificar tipos das colunas

df_spk.show()

df_spk.select('*').describe().show() #análise estatística simples

#Contagem de nulos
for c in df_spk.columns:
  print(c, df_spk.filter(F.col(c).isNull()).count())

df_spk = df_spk.withColumn("AnoMes",df_spk["AnoMes"].cast(StringType())) #Transformando ano em string

df_spk.show()



df_spk=df_spk.withColumn('AnoMes', F.concat(df_spk.AnoMes.substr(1, 4),
                                   F.lit('-'),
                                   df_spk.AnoMes.substr(5, 2))) #juntando ano e mês

df_spk.show(5)

df = df_spk

df = df.withColumn("AnoMes",F.to_date(F.col("AnoMes"),"yyyy-MM")) # passando para data

df_spk = df

df.show(100)

df_spk.printSchema()

df_spk = df_spk.withColumn("Ativo_Total", F.round(df_spk.Ativo_Total, 2))

df_spk = (df_spk.withColumn("Captações", F.round(df_spk.Captações, 2))
                .withColumn("Ativo_Total", F.round(df_spk.Ativo_Total, 2))
                .withColumn("Carteira_de_Crédito_Classificada", F.round(df_spk.Carteira_de_Crédito_Classificada, 2))
                .withColumn("Lucro_Líquido", F.round(df_spk.Lucro_Líquido, 2))
                .withColumn("Passivo_Circulante_e_Exigível_a_Longo_Prazo_e_Resultados_de_Exercícios_Futuros", F.round(df_spk.Passivo_Circulante_e_Exigível_a_Longo_Prazo_e_Resultados_de_Exercícios_Futuros, 2))
                .withColumn("Patrimônio_Líquido", F.round(df_spk.Patrimônio_Líquido, 2)))

df_spk.show(100)

df_spk.describe().show()

#Substitui Na
df_spk = df_spk.na.fill(0, subset=['Ativo_Total','Captações','Carteira_de_Crédito_Classificada','Lucro_Líquido','Passivo_Circulante_e_Exigível_a_Longo_Prazo_e_Resultados_de_Exercícios_Futuros','Patrimônio_Líquido'])

for c in df_spk.columns:
  print(c, df_spk.filter(F.col(c).isNull()).count())

df_spk = df_spk.na.fill('Na', subset=['SegmentoTb','Atividade'])

df_spk.groupBy("NomeInstituicao","Uf","Municipio") \
    .sum("Lucro_Líquido","Passivo_Circulante_e_Exigível_a_Longo_Prazo_e_Resultados_de_Exercícios_Futuros","Patrimônio_Líquido") \
    .show(100)

df_spk = df_spk.na.fill('Na', subset=["Uf",'Municipio'])

for c in df_spk.columns:
  print(c, df_spk.filter(F.col(c).isNull()).count())

df_spk = (df_spk.withColumnRenamed('Carteira_de_Crédito_Classificada','Cart_Cred_Classif')           
                .withColumnRenamed('Passivo_Circulante_e_Exigível_a_Longo_Prazo_e_Resultados_de_Exercícios_Futuros','PassCircExigLongPrzResExer_Fut'))

df_spk.describe().show()

df_spk.groupBy('NomeInstituicao').count().sort("count",ascending=False).show(200,truncate=False)

#procurando dados
df_spk = df_spk.filter(~F.col("NomeInstituicao").like("COOPERATIVA%"))

df_spk.groupBy('NomeInstituicao').count().sort("count",ascending=False).show(200,truncate=False)

df_spk.write.parquet("gs://group_one_bucket/arquivos_tratados/Inst_Fin_Resumo/resumo_py.parquet")

"""### **Emprestimos_PY**"""

spark = (                                       # CRIANDO A SESSÃO SPARK
    SparkSession.builder
                .master("local[*]")
                .appName("prj_final")
                .config("spark.ui.port", "4050")
                .config("spark.jars", 'https://storage.googleapis.com/hadoop-lib/gcs/gcs-connector-hadoop3-latest.jar')
                .getOrCreate()
)

spark # VERIFICANDO  A SESSÃO E A VERSÃO

df_spk_emp= spark.read.parquet("gs://group_one_bucket/arquivos_tratados/emprestimos/emprestimos_2019-2021_pd.parquet/part-00000-174e597c-126e-43f2-8a8f-7faf415fc6e9-c000.snappy.parquet")

df_spk_emp.printSchema()

df_spk_emp.select('*').describe().show()

for c in df_spk_emp.columns:
  print(c, df_spk_emp.filter(F.col(c).isNull()).count())

df_spk_emp.write.parquet("gs://group_one_bucket/arquivos_tratados/emprestimos/Emprestimos_PD.parquet")

"""## SPARK SQL"""

df_spk = spark.read.parquet("gs://group_one_bucket/arquivos_tratados/Inst_Fin_Resumo/resumo_py.parquet/part-00000-2c55a475-0898-41d8-a8a4-2970219dcce8-c000.snappy.parquet")

df_spk.printSchema()

df_spk = (df_spk.withColumnRenamed('Lucro_Líquido','Lucro_Liquido')           # RETIRANDO ACENTOS
                .withColumnRenamed('Patrimônio_Líquido','Patrimonio_Liquido')
       )

df_spk.printSchema()

df_spk.show()

df_spk.createOrReplaceTempView("SQL") # CRIANDO UMA TABELA TEMPORÁRIA PARA EXIBIR A CONSULTA EM SPARK SQL

spark.sql(
    'SELECT NomeInstituicao , MAX(Patrimonio_Liquido) AS Patrimonio_LQ, SUM(Lucro_Liquido) AS LucroLQ , MAX(Cart_Cred_Classif) AS CartCredito FROM SQL \
     GROUP BY NomeInstituicao \
    ORDER BY (SUM(Lucro_Liquido)) DESC'
         ).show(100)

#BUSCANDO DETERMINAR QUAIS OS MAIORES BANCOS A SEREM SELECIONADOS PARA O INSIGHT

spark.sql(
    'SELECT NomeInstituicao , MIN(Patrimonio_Liquido) AS Patrimonio_LQ, SUM(Lucro_Liquido) AS LucroLQ , MIN(Cart_Cred_Classif) AS CartCredito FROM SQL \
     GROUP BY NomeInstituicao \
    ORDER BY (MIN(Cart_Cred_Classif)) ASC'
         ).show(100)   #DETERMINANDO A CAUDA DA BASE DE DADOS PARA O INSIGHT

spark.sql(
    'SELECT NomeInstituicao, MIN(Patrimonio_Liquido) AS PatrimonioLQ, \
     MIN(Lucro_Liquido) AS MinLucro, MAX(Lucro_Liquido) AS MaxLucro FROM SQL \
     WHERE Lucro_Liquido < 0 \
     GROUP BY NomeInstituicao \
     ORDER BY MIN(Lucro_Liquido)'
).show(100)  #VERIFICANDO OS BANCOS QUE TIVERAM LUCRO NEGATIVO

spark.sql(
    'SELECT NomeInstituicao, MIN(Patrimonio_Liquido) AS PatrimonioLQ, \
     MIN(Lucro_Liquido) AS MinLucro, MAX(Lucro_Liquido) AS MaxLucro FROM SQL \
     WHERE Lucro_Liquido > 0 \
     GROUP BY NomeInstituicao \
     ORDER BY MIN(Lucro_Liquido) ASC'
).show(100)  #VERIFICANDO OS BANCOS QUE POSSUEM BAIXO PATRIMONIO MAS COM LUCROS POSITIVOS ... BUSCANCO RELAÇÃO COM OS DIGITAIS

df_spk.printSchema()

spark.sql(
    'SELECT NomeInstituicao, MIN(Cart_Cred_Classif) AS CartCredito, \
     MIN(Ativo_Total) AS AtivoTot, MAX(Lucro_Liquido) AS MaxLucro FROM SQL \
     WHERE Lucro_Liquido > 0 AND Lucro_Liquido <> 0\
     GROUP BY NomeInstituicao \
     ORDER BY AVG(Lucro_Liquido) DESC'
).show(100)  #OBSERVANDO A CORRELAÇÃO ENTRE A CARTEIRA DE CRÉDITO, ATIVOS E O LUCRO DOS BANCOS

df_spk.printSchema()

from pyspark.sql.functions import *

(df_spk.select("Atividade")  # VERIFICANDO VALORES ÚNICOS DO CAMPO ATIVIDADE
.where(col("Atividade").isNotNull())
.agg(countDistinct("Atividade").alias("QTD_Atividades"))
.show())

(df_spk.select("SegmentoTb")  # VERIFICANDO OS SEGMENTOS NÃO NULOS
.where(col("SegmentoTb").isNotNull())
.distinct()
.show(50, False))

(df_spk  # AGRUPANDO POR SEGMENTO NÃO NULO E CONTANDO OS VÁLIDOS
.select("SegmentoTB")
.where(col("SegmentoTB").isNotNull())
.groupBy("SegmentoTB")
.count()
.orderBy("count", ascending=False)
.show(n=50, truncate=False))

(df_spk  # OBSERVANDO AS INSTITUIÇÕES POR ATIVIDADE
.select("NomeInstituicao", "SegmentoTb", "Atividade")
.show(50, False))

(df_spk # ANALISANDO A CORRELAÇÃO ENTRE CARTEIRA DE CRÉDITO E LUCRO
.select(F.sum("Cart_Cred_Classif"), F.avg("Lucro_Liquido"),
F.min("Lucro_Liquido"), F.max("Lucro_Liquido"))
.show())



spark.sql("""SELECT  NomeInstituicao, SegmentoTB, Atividade
FROM SQL WHERE Lucro_Liquido > 0
ORDER BY Lucro_Liquido DESC""").show(50) # BUSCANDO INSTIUTIÇÕES POR SEGMENTO E ATIVIDADE COM LUCROS POSITIVOS

spark.sql("SET -v").select("key", "value").show(n=5, truncate=False) # CONFERINDO A VERSÃO DO SPARK SQL



"""## PANDAS

### CONFIGS
"""

pd.set_option("max_columns",None) #  SETANDO AMBIENTE PANDA PARA NÃO TER LIMITE NA EXIBIÇÃO DAS COLUNAS

pd.options.display.float_format = '{:.2f}'.format # FORMATANDO A EXIBIÇÃO EM DUAS CASAS DECIMAIS

serviceAccount = r"/tmp/key.json"

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = serviceAccount

"""### B3 2019"""

#Leitura do dataset a partir do Cloud Storage e o atribuindo a uma variável
df = pd.read_csv('https://storage.googleapis.com/group_one_bucket/arquivos_brutos/B3_bancos_Bruto/B32019.csv', header=None, sep=';')

#Demonstração do dataset
df.head()

#Vendo a quantidade de linhas e colunas do dataset
df.shape

#Mostrando cada valor único de uma coluna especifica para ver se é encontrado alguma inconsistência
sorted(pd.unique(df[3]))

#Criando uma nova variável onde sera mostrados apenas as linhas e colunam quem possuam os valores definidos
 df2 = df.loc[df[3].isin(['ITUB3', 'ITUB4', 'BBDC3', 'BBDC4', 'BBAS3', 'SANB11', 'SANB3', 'SANB4', 'BPAC11', 'BIDI11', 'BIDI4', 'BIDI3', 'BMGB4', 'BRSR3', 'BPAN4', 'ABCB4', 'BMEB3', 'BMEB4', 'BNBR3', 'BSLI3', 'BSLI4', 
'BEES3', 'BEES4', 'BPAR3', 'BAZA3', 'BRIV3', 'BRIV4', 'PINE3', 'PINE4', 'BGIP3', 'BGIP4', 'IDVL3', 'IDVL4', 'NUBR33', 'MODL11', 'BMGB3', 'BRBI11', 'ITSA4', 'MODL3', 'MODL4', 'RPAD3', 'RPAD5', 'RPAD6', 'CRIV3', 'CRIV4', 
'MERC4'])].copy()

sorted(pd.unique(df2[5]))

df2.shape

#Vendo a quantidade de valores Nulos
df2.isnull().sum()

sorted(pd.unique(df2[1]))
# 0 - apenas 1, 2 -  apenas 2.0, 4 - apenas 10, 7 -  apenas nan, 8 - apenas R$, 19 - apenas 0.0, 20 - apenas 0.0, 22 - apenas 1.0, 23 - apenas 0

#Dropando/Removendo colunas específicas
df2.drop([0, 2, 4, 6, 7, 8, 19, 20, 21, 22, 23],axis=1,inplace=True)

#Vendo as informações
df2.info()

df2.tail()

#Listando as colunas do dataset
df2.columns.to_list()

#Dicionário com os nomes da tabelas e os nomes para quais serão mudados
dict = { 1 : 'DATA', 3: 'CODNEG', 5: 'NOMES', 9: 'ABERTURA', 10: 'MAXIMO', 11: 'MINIMO', 12: 'MEDIO', 13: 'ULTIMO', 14: 'PREOFC', 15: 'PREOFV', 16: 'TOTNEG', 17: 'QUATOT', 18: 'VOLTOT', 24: 'CODISI',
25: 'DISMES'}

#Renomenado as colunas a partir do dicionário
df2.rename(columns=dict, inplace=True)

df2

#Mudando uma coluna para o formato Datetime e definindo a ordem e separador do mesmo
df2['DATA'] = df2['DATA'].apply(lambda x: datetime.strftime(pd.to_datetime(x,format='%Y%m%d'), '%Y-%m-%d'))

df2

sorted(pd.unique(df2['NOMES']))

sorted(pd.unique(df2['CODNEG']))

#Subindo os dataset tratado para o Cloud Storage em Csv
df2.to_csv("gs://group_one_bucket/arquivos_tratados/B3_Bancos_Tratado/B3_2019_Bancos_Tratado.csv", index=False)

"""### B3 2020"""

df3 = pd.read_csv('https://storage.googleapis.com/group_one_bucket/arquivos_brutos/B3_bancos_Bruto/B32020.csv', header=None, sep=';')

df3.head()

df3.shape

df4 = df3.loc[df3[5].isin(['ITUB3', 'ITUB4', 'BBDC3', 'BBDC4', 'BBAS3', 'SANB11', 'SANB3', 'SANB4', 'BPAC11', 'BIDI11', 'BIDI4', 'BIDI3', 'BMGB4', 'BRSR3', 'BPAN4', 'ABCB4', 'BMEB3', 'BMEB4', 'BNBR3', 'BSLI3', 'BSLI4', 
'BEES3', 'BEES4', 'BPAR3', 'BAZA3', 'BRIV3', 'BRIV4', 'PINE3', 'PINE4', 'BGIP3', 'BGIP4', 'IDVL3', 'IDVL4', 'NUBR33', 'MODL11', 'BMGB3', 'BRBI11', 'ITSA4', 'MODL3', 'MODL4', 'RPAD3', 'RPAD5', 'RPAD6', 'CRIV3', 'CRIV4', 
'MERC4'])].copy()

df4.shape

sorted(pd.unique(df4[3]))
#0 - apenas 1, 1 - apenas 2020, 4 - apenas 2, 6 - apenas 10, 9 - apenas nan, 10 - apenas R$, 21 - apenas 0, 22 -  apenas 0, 23, apenas 99991231, 24 - apenas 1, 25 - apenas 0

df4.drop([0, 4, 6, 8, 9, 10, 21, 22, 23, 24, 25],axis=1,inplace=True)

df4.columns.to_list()

dict = {5: 'CODNEG', 7:'NOMES', 11: 'ABERTURA', 12 :'MAXIMO',13: 'MINIMO', 14: 'MEDIO', 15: 'ULTIMO', 16: 'PREOFC', 17: 'PREOFV', 18: 'TOTNEG', 19: 'QUATOT',20: 'VOLTOT', 26: 'CODISI',27: 'DISMES'}

df4.rename(columns=dict, inplace=True)

df4

#Juntando colunas separadas em uma e definindo o separador
cols = [1, 2, 3]
df4['DATA'] = df4[cols].apply(lambda row: '-'.join(row.values.astype(str)), axis=1)

df4['DATA'] = df4['DATA'].apply(lambda x: pd.to_datetime(x,format='%Y-%m-%d'))

#Retorna a coluna e a remove do dataset
data = df4.pop('DATA')

df4.drop([1, 2, 3],axis=1,inplace=True)

#Inserindo uma coluna em um local específico
df4.insert(0, 'DATA', data)

df4.head()

df4.info()

sorted(pd.unique(df4['NOMES']))

sorted(pd.unique(df4['CODNEG']))

df4.to_csv("gs://group_one_bucket/arquivos_tratados/B3_Bancos_Tratado/B3_2020_Bancos_Tratados.csv", index=False)



"""### B3 2021"""

df5 = pd.read_csv('https://storage.googleapis.com/group_one_bucket/arquivos_brutos/B3_bancos_Bruto/B3_2021.csv', sep=',')

df5.head()

df5.shape

sorted(pd.unique(df5['CODNEG']))

#Removendo espaços de valores dentro de uma coluna
df5['CODNEG'] = df5['CODNEG'].str.strip()

df6 = df5.loc[df5['CODNEG'].isin(['ITUB3', 'ITUB4', 'BBDC3', 'BBDC4', 'BBAS3', 'SANB11', 'SANB3', 'SANB4', 'BPAC11', 'BIDI11', 'BIDI4', 'BIDI3', 'BMGB4', 'BRSR3', 'BPAN4', 'ABCB4', 'BMEB3', 'BMEB4', 'BNBR3', 'BSLI3', 'BSLI4', 
'BEES3', 'BEES4', 'BPAR3', 'BAZA3', 'BRIV3', 'BRIV4', 'PINE3', 'PINE4', 'BGIP3', 'BGIP4', 'IDVL3', 'IDVL4', 'NUBR33', 'MODL11', 'BMGB3', 'BRBI11', 'ITSA4', 'MODL3', 'MODL4', 'RPAD3', 'RPAD5', 'RPAD6', 'CRIV3', 'CRIV4', 
'MERC4'])].copy()

df6.columns

sorted(pd.unique(df6['PTOEXE']))
#TIPREG - apenas 1, CODBDI -  apenas 2, TPMERC - apenas 10, PRAZOT - apenas '    ', MOEDA - apenas R$, PREEXE - apenas 0, INDOPC -  apenas 0, DATVEN	- apenas 99991231, FATCOT - apenas 1, PTOEXE -  apenas 0

df6.drop(['TIPREG', 'CODBDI', 'TPMERC', 'ESPECI', 'PRAZOT', 'MOEDA', 'PREEXE', 'INDOPC', 'DATVEN', 'FATCOT', 'PTOEXE'],axis=1,inplace=True)

df6.head()

cols = ['ANO', 'MES', 'DIA']
df6['DATA'] = df6[cols].apply(lambda row: '-'.join(row.values.astype(str)), axis=1)

df6.drop(['ANO', 'MES', 'DIA'],axis=1,inplace=True)

data = df6.pop('DATA')

df6.insert(0,'DATA',data)

df6['DATA'] = df6['DATA'].apply(lambda x: pd.to_datetime(x,format='%Y-%m-%d'))

df6.head()

df6.shape

df6['NOMES'] = df6['NOMES'].str.strip()

sorted(pd.unique(df6['NOMES']))

sorted(pd.unique(df6['CODNEG']))

pandas_profiling.ProfileReport(df6,minimal=True)

df6.to_csv("gs://group_one_bucket/arquivos_tratados/B3_Bancos_Tratado/B3_2021_Bancos_Tratados.csv", index=False)

"""### B3 2022"""

df7 = pd.read_csv('https://storage.googleapis.com/group_one_bucket/arquivos_brutos/B3_bancos_Bruto/B32022.csv', header=None, sep=';')

df7

df7.shape

df8 = df7.loc[df7[5].isin(['ITUB3', 'ITUB4', 'BBDC3', 'BBDC4', 'BBAS3', 'SANB11', 'SANB3', 'SANB4', 'BPAC11', 'BIDI11', 'BIDI4', 'BIDI3', 'BMGB4', 'BRSR3', 'BPAN4', 'ABCB4', 'BMEB3', 'BMEB4', 'BNBR3', 'BSLI3', 'BSLI4', 
'BEES3', 'BEES4', 'BPAR3', 'BAZA3', 'BRIV3', 'BRIV4', 'PINE3', 'PINE4', 'BGIP3', 'BGIP4', 'IDVL3', 'IDVL4', 'NUBR33', 'MODL11', 'BMGB3', 'BRBI11', 'ITSA4', 'MODL3', 'MODL4', 'RPAD3', 'RPAD5', 'RPAD6', 'CRIV3', 'CRIV4', 
'MERC4', 'NASDAQ'])].copy()

sorted(pd.unique(df8[5]))
#0 - apenas 1, 4 - apenas 2.0, 6 - apenas 10, 9 - apenas R$, 20 - apenas 0.0, 21 - apenas 0.0, 22 -  apenas 99991231.0, 23 - apenas 1.0, 24 - apenas 0

df8.drop([0, 4, 6, 8, 9, 20, 21, 22, 23, 24],axis=1,inplace=True)

df8.head()

cols = [3, 2, 1]
df8['DATA'] = df8[cols].apply(lambda row: '-'.join(row.values.astype(str)), axis=1)

df8.drop([1, 2, 3],axis=1,inplace=True)

df8['DATA'].apply(lambda x: pd.to_datetime(x,format='%d-%m-%Y'))

df8['DATA'] = df8['DATA'].apply(lambda x: pd.to_datetime(x,format='%d-%m-%Y'))

data = df8.pop('DATA')

df8.insert(0,'DATA',data)

df8.head()

dict = {26: 'DISMES', 25: 'CODISI', 19: 'VOLTOT', 18:'QUATOT', 17:'TOTNEG', 16: 'PREOFV', 15: 'PREOFC', 14: 'ULTIMO', 13:'MEDIO', 12:'MINIMO', 11: 'MAXIMO', 10: 'ABERTURA', 7: 'NOMES', 5: 'CODNEG'}

df8.rename(columns=dict, inplace=True)

df8.head()

df8.shape

df8.rename(columns={'QUALTOT':'QUATOT'},inplace=True)

#Substituindo a vírgula por um ponto em uma coluna
df8['VOLTOT'].replace(r',','.',regex=True,inplace=True)

#Fazendo com que uma coluna receba o tipo inteiro
df8['VOLTOT'] = pd.to_numeric(df8['VOLTOT'],downcast='integer')

sorted(pd.unique(df8['NOMES']))

sorted(pd.unique(df8['CODNEG']))

df8.replace({'ABC BRASIL  P':'ABC BRASIL',
 'ALFA FINANC O':'ALFA FINANC',
 'ALFA FINANC P':'ALFA FINANC',
 'ALFA HOLDINGO':'ALFA HOLDING',
 'ALFA HOLDINGP':'ALFA HOLDING',
 'ALFA INVEST O':'ALFA INVEST',
 'ALFA INVEST P':'ALFA INVEST',
 'AMAZONIA    O':'AMAZONIA',
 'BANCO BMG   P':'BANCO BMG',
 'BANCO INTER O':'BANCO INTER',
 'BANCO INTER P':'BANCO INTER',
 'BANCO INTER U':'BANCO INTER',
 'BANCO PAN   P':'BANCO PAN',
 'BANESE      O':'BANESE',
 'BANESE      P':'BANESE',
 'BANESTES    O':'BANESTES',
 'BANESTES    P':'BANESTES',
 'BANRISUL    O':'BANRISUL',
 'BR PARTNERS U':'BR PARTNERS',
 'BRADESCO    O':'BRADESCO',
 'BRADESCO    P':'BRADESCO',
 'BRASIL      O':'BRASIL',
 'BRB BANCO   O':'BRB BANCO',
 'BRB BANCO   P':'BRB BANCO',
 'BTGP BANCO  U':'BTGP BANCO',
 'ITAUSA      P':'ITAUSA',
 'ITAUUNIBANCOO':'ITAUUNIBANCO',
 'ITAUUNIBANCOP':'ITAUUNIBANCO',
 'MERC BRASIL O':'MERC BRASIL',
 'MERC BRASIL P':'MERC BRASIL',
 'MERC FINANC P':'MERC FINANC',
 'MODALMAIS   O':'MODALMAIS',
 'MODALMAIS   P':'MODALMAIS',
 'MODALMAIS   U':'MODALMAIS',
 'NORD BRASIL O':'NORD BRASIL',
 'NU-NUBANK   D':'NU-NUBANK',
 'PINE        P':'PINE',
 'SANTANDER BRO':'SANTANDER BR',
 'SANTANDER BRP':'SANTANDER BR',
 'SANTANDER BRU':'SANTANDER BR'}, inplace=True)

sorted(pd.unique(df8['NOMES']))

df8

df8.to_csv("gs://group_one_bucket/arquivos_tratados/B3_Bancos_Tratado/B3_2022_Bancos_Tratados.csv", index=False)

"""### Concat B3"""

#Juntando datasets já tratados em um único 
df_bancos = pd.concat([df8, df6, df4, df2])

df_bancos

df_bancos.rename(columns={"DATA": "PERIODO"}, inplace=True)

df_bancos.isnull().sum()

df_bancos['PERIODO'] = df_bancos['PERIODO'].apply(lambda x: pd.to_datetime(x,format='%Y-%m-%d'))

df_bancos['VOLTOT'].replace(r',','.',regex=True,inplace=True)

df_bancos['VOLTOT']= pd.to_numeric(df_bancos['VOLTOT'],downcast='integer')

pd.to_numeric(df_bancos.VOLTOT)

df_bancos.info()

#Fazendo o upload dos datasets já tratados e agrupados para Cloud Storage no formato parquet
df_bancos.to_parquet('gs://group_one_bucket/arquivos_tratados/B3_Bancos_Tratado/B3_bancos_new_PD.parquet', index=False)

"""### B3 TRATADOS"""

folder_path = r"gs://group_one_bucket/arquivos_tratados/B3_Bancos_Tratado/"
file_list = gcsfs.GCSFileSystem(token=serviceAccount).glob(folder_path + "*.csv")
file_list = [os.path.join(r"gs://" + _) for _ in file_list]

df_b3t = (pd.concat((pd.read_csv(f, parse_dates=['DATA']) for f in file_list)))

df_b3t['VOLTOT'].replace(r',','.',regex=True,inplace=True)

df_b3t['VOLTOT']= pd.to_numeric(df_b3t['VOLTOT'],downcast='integer')

df_b3t.info()

df_b3t.to_parquet(r"gs://group_one_bucket/arquivos_tratados/B3_Bancos_Tratado/B3_bancos.parquet", index=False)

"""### NOMES DAS INSTITUIÇÕES FINANCEIRAS"""

quadrimestre = pd.date_range(start="2019-03", end="2021-10", freq="3M")  # CRIANDO UMA LISTA DE DATAS PARA AUTOMATIZAR A CARGA DE DATA SET DO BANCO CENTRAL
quadrimestre = quadrimestre.strftime("%Y%m")
for anomes in quadrimestre:
  nomes_path = f"https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata/IfDataCadastro(AnoMes=@AnoMes)?@AnoMes={anomes}&$format=text/csv&$select=CodInst,NomeInstituicao,SegmentoTb,Atividade,Uf,Municipio,Situacao"

  nomes = pd.read_csv(nomes_path, sep=",")
  nomes.to_csv("gs://group_one_bucket/arquivos_brutos/nomes_bancos/listagem_bancos.csv", mode='a', index=False)
  time.sleep(30)

nomes = pd.read_csv('gs://group_one_bucket/arquivos_brutos/nomes_bancos/listagem_bancos.csv', sep=",")

nomes.to_csv("gs://group_one_bucket/arquivos_brutos/listagem_bancos.csv", index=False)

"""### CARTEIRA DE CRÉDITOS"""

folder_path = r"gs://group_one_bucket/arquivos_brutos/carteira_credito_bancos/"
file_list = gcsfs.GCSFileSystem(token=serviceAccount).glob(os.path.join(folder_path,"*.json"))
file_list = [os.path.join(r"gs://", _) for _ in file_list]

df_creditos = (pd.concat((pd.read_json(f,lines=True) for f in file_list)))

file_list

df_creditos = nomes.set_index('CodInst').join(df_creditos.set_index('CodInst'), how='right') # REALIZANDO UM JOIN DOS DATA SETS CAPTURADOS.

df_creditos.reset_index(inplace=True)

df_creditos[df_creditos.NomeInstituicao.isnull()]

df_creditos = pd.read_parquet('gs://group_one_bucket/arquivos_brutos/carteira_credito_bancos/carteira_creditos.parquet')

df_creditos

df_creditos.to_parquet('gs://group_one_bucket/arquivos_brutos/carteira_credito_bancos/carteira_creditos.parquet')

"""### DRE - INSTITUIÇÕES FINANCEIRAS"""

folder_path = r"gs://group_one_bucket/arquivos_brutos/Demonstrativo_TOT/"
file_list = gcsfs.GCSFileSystem(token=serviceAccount).glob(folder_path + "*.json")
file_list = [os.path.join(r"gs://" + _) for _ in file_list]

df_dr = (pd.concat((pd.read_json(f,lines=True) for f in file_list))) # REALIZANDO A CONCATENAÇÃO DOS DATA SETS

dr_all = nomes.set_index('CodInst').join(df_dr.set_index('CodInst'), on='CodInst', how='inner') # FAZENDO UM JOIN PARA JUNTAR TODOS EM UMA ÚNICA BASE

dr_all.reset_index(inplace=True)

#dr_all.to_parquet(r"gs://group_one_bucket/arquivos_tratados/Inst_Fin_Demonstrativo/dre.parquet", index=False)

"""### **DEMONSTRATIVO TRATADO PD**"""

folder_path = r"gs://group_one_bucket/arquivos_brutos/Demonstrativo_TOT/"
file_list = gcsfs.GCSFileSystem(token=serviceAccount).glob(folder_path + "*.json")
file_list = [os.path.join(r"gs://" + _) for _ in file_list]        # CRIANDO UMA LISTA DOS DIRETÓRIOS EXISTENTES NA BUCKET

df_dr = (pd.concat((pd.read_json(f,lines=True) for f in file_list)))  # CONCATENANDO AS BASES EXISTENTES NA BUCKET

df_dr.head(100)

#nomes_path = "gs://group_one_bucket/arquivos_brutos/Instituições financeiras do IFDATA.csv"

nomes = pd.read_csv(nomes_path, sep=",")

#dr_all = nomes.set_index('CodInst').join(df_dr.set_index('CodInst'), on='CodInst', how='inner')

#dr_all.reset_index(inplace=True)

#backup = dr_all.copy()

#dr_all.rename(columns=lambda x: x.split('\n')[0],inplace=True)
#dr_all.rename(columns=lambda x: x.strip().replace(' ','_'),inplace=True)
#dr_all.columns.values[-5] = 'Receitas_de_Operações_de_Câmbio'
#dr_all.columns.values[-4] = 'Despesas_de_Operações_de_Câmbio'

#dr_all.to_parquet(r"gs://group_one_bucket/arquivos_tratados/Inst_Fin_Demonstrativo/dre2.parquet", index=False)

dre2_path = "gs://gs://group_one_bucket/arquivos_tratados/Inst_Fin_Demonstrativo/dre2.parquet"

df_dre = pd.read_parquet(dre2_path, engine='auto', columns=None, storage_options=None, use_nullable_dtypes=False)

pandas_profiling.ProfileReport(df_dr,minimal=True) # USANDO A API PROLIFING PARA EXAMINAR O DATAFRAME E POSSÍVEIS LIMPEZAS

df_dre.head(5)

df_dre.info()

df_dre.columns = df_dre.columns.str.replace(' ', '') # LIMPEZA DOS DADOS

df_dre.info()

pd.options.display.float_format = '{:.2f}'.format

print(df_dre.describe())

# RENOMENANDO E REDUZINDO O NOME DE COLUNAS

df_dre = df_dre.rename( columns = {'JurosSobreCapitalSocialdeCooperativas\n(k)':'Jur_Cap_SocCoop_K'})

df_dre = df_dre.rename( columns = {'ResultadodeProvisãoparaCréditosdeDifícilLiquidação\n(b5)':'Res_Prov_Cred_Dif_Liq_B5'})

df_dre = df_dre.rename( columns = {'ResultadodeParticipações\n(d6)':'Res_Particpacoes_D6'})

df_dre = df_dre.rename( columns = {'ResultadodeOperaçõesdeCâmbio\n(b4)':'Res_Op_Cambio_B4', 'ResultadodeOperaçõesdeCâmbio\n(a5)':'Res_Op_Cambio_A5','ResultadodeIntermediaçãoFinanceira\n(c)=(a)+(b)':'Res_Intermed_Financ_C=A+B'})

df_dre = df_dre.rename( columns = {'ResultadoantesdaTributação,LucroeParticipação\n(g)=(e)+(f)':'Res_Antes_Trib_Lcr_Partic_G=E+F'})

df_dre = df_dre.rename( columns = {'ResultadoOperacional\n(e)=(c)+(d)':'Res_Oper_E=C+D','ResultadoNãoOperacional\n(f)':'Res_N_Oper_F','RendasdeTarifasBancárias\n(d2)':'Renda_Trf_Banc_D2','JurosSobreCapitalPróprio\n(k)':'Jur_Cpt_Proprio_K','ImpostodeRendaeContribuiçãoSocial\n(h)':'ImpRnd_ContrSoc_H','DespesasdePessoal\n(d3)':'Desp_Pessoal_D3'})

df_dre = df_dre.rename( columns = {'DespesasdeOperaçõesdeArrendamentoMercantil\n(b3)':'Desp_Oper_ArrMercantil_B3','DespesasdeObrigaçõesporEmpréstimoseRepasses\n(b2)':'Desp_Obrig_Emprest_e_Repasse_B2','DespesasdeIntermediaçãoFinanceira\n(b)=(b1)+(b2)+(b3)+(b4)+(b5)':'Desp_Interm_Financ_B=B1+B2+B3+B4+B5','DespesasdeCaptação\n(b1)':'Desp_Capta_B1','DespesasTributárias\n(d5)':'Desp_Trib_D5','DespesasAdministrativas\n(d4)':'Desp_Adm_D4'})

df_dre = df_dre.rename( columns = {'RendasdePrestaçãodeServiços\n(d1)':'Res_Prest_Srv_D1','RendasdeOperaçõesdeCrédito\n(a1)':'Res_Op_Credito_A1','RendasdeOperaçõesdeArrendamentoMercantil\n(a2)':'Renda_Arrend_Mercantil_A2','RendasdeOperaçõescomTVM\n(a3)':'Rend_Op_TVM_A3','RendasdeOperaçõescomInstrumentosFinanceirosDerivativos\n(a4)':'Rend_Op_Instr_Financ_Derivat_A4','RendasdeAplicaçõesCompulsórias\n(a6)':'Rend_Aplc_Compuls_A6'})

df_dre = df_dre.rename( columns = {'ReceitasdeIntermediaçãoFinanceira\n(a)=(a1)+(a2)+(a3)+(a4)+(a5)+(a6)':'Rec_Interm_Financ_A=A1+A2+A3+A4+A5+A6','ParticipaçãonosLucros\n(i)':'Partic_Lucros_I','OutrasReceitas/DespesasOperacionais\n(d)=(d1)+(d2)+(d3)+(d4)+(d5)+(d6)+(d7)+(d8)':'Outras_Rec_Desp_Op_D=D1+D2+D3+D4+D5+D6+D7+D8','OutrasReceitasOperacionais\n(d7)':'Outras_Rec_Op_D7','OutrasDespesasOperacionais\n(d8)':'Outras_Desp_Op_D8','LucroLíquido\n(j)=(g)+(h)+(i)':'Lucro_Lq_J=G+H+I'})

df_dre.info()

df_dre[df_dre.duplicated()].shape[0] # VERIFICANDO LINHAS DUPLICADAS

df_dre.isna().sum() # VERIFICANDO CAMPOS NULOS

print(df_dre.describe())

df_dre.drop(["Jur_Cpt_Proprio_K", "Jur_Cap_SocCoop_K"], axis=1, inplace=True)

df_dre.isna().mean() # MÉDIA DE NULOS POR COLUNA

df_dre.info()

# LIMPANDO OS NULOS E CORRIGINDO ZEROS

df_dre.update(df_dre['Atividade'].fillna('Não Informado'))

df_dre.update(df_dre['SegmentoTb'].fillna('Não Informado'))

df_dre.update(df_dre['Uf'].fillna('NaN'))

df_dre.update(df_dre.fillna(0))

df_situacao = df_dre.groupby("Situacao")['Situacao'].count()

df_bkp=df_dre.copy()

# RETIRANDO LINHAS COM INATIVOS

df_situacao

Drop_Inativos = df_dre[ df_dre['Situacao'] == 'I' ].index

df_dre.drop(Drop_Inativos , inplace=True)

df_situacao = df_dre.groupby("Situacao")['Situacao'].count()

df_situacao

df_dre.info()

df_situacao = df_dre.groupby("NomeInstituicao")['Res_Antes_Trib_Lcr_Partic_G=E+F'].sum().sort_values(ascending=False)

df_situacao2 = df_dre.groupby("SegmentoTb")['SegmentoTb'].count()

df_situacao2.head(20)

df_naoinf = df_dre[df_dre['SegmentoTb'] == 'Não Informado']

df_naoinf

# DROPANDO LINHAS QUE NÃO SERÃO ANALISADAS NO PROJETO

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Sociedade de Crédito Imobiliário - Repassadora'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Sociedade de Arrendamento Mercantil'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Sociedade Distribuidora de TVM'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Sociedade Corretora de TVM'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Sociedade Corretora de Câmbio'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Companhia Hipotecária'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Companhia Hipotecária'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

pd.set_option("max_rows",None) # SETANDO PARA NÃO TER LIMITES DE LINHAS

df_situacao2.head(20)

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Agência de Fomento'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Banco Comercial Estrangeiro - Filial no país'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Sociedade de Crédito ao Microempreendedor'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

Drop_SegmentoTb = df_dre[ df_dre['SegmentoTb'] == 'Agência de Fomento'].index

df_dre.drop(Drop_SegmentoTb , inplace=True)

df_situacao2.head(20)

df_dre.describe(include = 'all')

# AJUSTANDO A FORMATOS E ALTERANDO PARA CAMPOS DATAS

df_dre['AnoMes'] = df_dre['AnoMes'].astype(str)

df_dre['AnoMes'] = pd.to_datetime(df_dre['AnoMes'], format='%Y-%m-%d')

df_dre['AnoMes'] = pd.to_datetime(df_dre['AnoMes']).dt.normalize()

df_dre.head(5)

df_dre.info()

df_dre.nunique()

df_dre['NomeInstituicao'].unique()

df_dre.NomeInstituicao.value_counts()

df_COOPER = df_dre.loc[['COOPER' in x for x in df_dre['NomeInstituicao']]] # CRIANDO UMA LISTA DOS ÍNDICES DOS CAMPOS COM NOME DE COOPERATIVA

df_dre = df_dre.drop(df_COOPER.index) # ELIMINANDO AS LINHAS DAS COOPERATIVAS

df_dre.NomeInstituicao.value_counts()

df_dre['Atividade'].unique()

df_dre.Atividade.value_counts()

#df_IPEMISSOR = df_dre.loc[['IP Emissor Pós-Pago' in x for x in df_dre['Atividade']]]
#df_dre = df_dre.drop(df_IPEMISSOR.index)

#df_IPCREDENCIADORA = df_dre.loc[['IP Credenciadora' in x for x in df_dre['Atividade']]]
#df_dre = df_dre.drop(df_IPCREDENCIADORA.index)

df_dre.Atividade.value_counts()

df_BNDESdesn = df_dre.loc[['Desenvolvimento - exceto BNDES' in x for x in df_dre['Atividade']]]
df_dre = df_dre.drop(df_BNDESdesn.index)

df_BNDESdes = df_dre.loc[['Desenvolvimento - BNDES' in x for x in df_dre['Atividade']]]
df_dre = df_dre.drop(df_BNDESdes.index)

df_BNDESn = df_dre.loc[['Indústria - Não BNDES' in x for x in df_dre['Atividade']]]
df_dre = df_dre.drop(df_BNDESn.index)

df_BNDES = df_dre.loc[['Indústria - BNDES' in x for x in df_dre['Atividade']]]
df_dre = df_dre.drop(df_BNDES.index)

df_cambio = df_dre[df_dre['Atividade']=='Cambio']

df_dre = df_dre.drop(df_cambio.index)

df_cambio.NomeInstituicao.value_counts()

df_credatac = df_dre[df_dre['Atividade']=='Crédito Atacado']

df_credatac.NomeInstituicao.value_counts()

df_servicos = df_dre[df_dre['Atividade']=='Serviços']

#ORIGINAL NU PAGAMENTOS S.A. MODAL  INTER AGIBANK  PAN BANCO BMG

df_servicos.NomeInstituicao.value_counts()

df_dre.NomeInstituicao.value_counts()

df_dre.columns

Despesas = [ 'AnoMes','Desp_Pessoal_D3','Desp_Adm_D4','Desp_Interm_Financ_B=B1+B2+B3+B4+B5','Outras_Rec_Desp_Op_D=D1+D2+D3+D4+D5+D6+D7+D8']



df_dre = df_dre.sort_values(by = 'Lucro_Lq_J=G+H+I', ascending = False).reset_index(drop=True)

#df_dre

df_dre.info()

df_dre.groupby(by = 'NomeInstituicao')['Lucro_Lq_J=G+H+I'].agg([np.mean, np.median]).T

df_dre['Ano'] = df_dre['AnoMes'].dt.year

df_dre['Mes'] = df_dre['AnoMes'].dt.month

df_dre.groupby(['Mes']).describe()['Lucro_Lq_J=G+H+I']

plt.figure( figsize=(18,18) )
sns.boxplot( data=df_dre, x='Mes', y='Lucro_Lq_J=G+H+I' ) # PLOTANDO O GRÁFICO PARA VERIFICAR OUTLIERS

df_dre.groupby(['Ano']).describe()['Lucro_Lq_J=G+H+I']

plt.figure( figsize=(18,18) )
sns.boxplot( data=df_dre, x='Ano', y='Lucro_Lq_J=G+H+I' )

df_dre.groupby(['Mes']).describe()['Outras_Rec_Desp_Op_D=D1+D2+D3+D4+D5+D6+D7+D8']

plt.figure( figsize=(18,18) )
sns.boxplot( data=df_dre, x='Mes', y='Outras_Rec_Desp_Op_D=D1+D2+D3+D4+D5+D6+D7+D8' )

df_dre.groupby(['Ano']).describe()['Outras_Rec_Desp_Op_D=D1+D2+D3+D4+D5+D6+D7+D8']

plt.figure( figsize=(18,18) )
sns.boxplot( data=df_dre, x='Ano', y='Outras_Rec_Desp_Op_D=D1+D2+D3+D4+D5+D6+D7+D8' )

sns.boxplot( data=df_dre, x='Outras_Rec_Desp_Op_D=D1+D2+D3+D4+D5+D6+D7+D8')

sns.boxplot( data=df_dre, x='Lucro_Lq_J=G+H+I')

!pip install --upgrade plotly

!pip install chart-studio

import plotly.graph_objects as go

import matplotlib.pyplot as plt

# Commented out IPython magic to ensure Python compatibility.
import seaborn as sns
import matplotlib.pyplot as plt
# %matplotlib inline
import warnings
warnings.filterwarnings('ignore')

sns.heatmap( df_dre.corr( 'spearman' ), annot=True ) # USANDO O MÉTODO SPEARMAN PARA OBSERVAR AS CORRELAÇÕES

plt.subplots(figsize=(18,13))
sns.heatmap(df_dre.corr(), annot=True, cmap='plasma', linecolor='gray', linewidths=1); # OBSERVANDO AS CORRELAÇÕES DOS VALORES

#sns.set(rc = {'figure.figsize':(18,10)})
#sns.heatmap(df_dre.corr(),annot=True,linewidths=4)

sns.heatmap( df_dre.corr( 'spearman' ), annot=True )

df_dre.corr()



df_dre.to_parquet(r"gs://gs://group_one_bucket/arquivos_tratados/Inst_Fin_Demonstrativo/dre2_pd.parquet", index=False, storage_options={'token':serviceAccount})



"""### RESUMO DAS INSTITUIÇÕES FINANCEIRAS"""

pasta_com_resumos = r"gs://group_one_bucket/arquivos_brutos/InstituicoesFinanceiras_TOT/"

lista_jsons = gcsfs.GCSFileSystem(token=serviceAccount).glob(pasta_com_resumos + "*.json")
lista_jsons = [os.path.join(r"gs://" + _) for _ in lista_jsons]

df_resumo = pd.concat((pd.read_json(f,lines=True) for f in lista_jsons))

df_resumo = nomes.set_index('CodInst').join(df_resumo.set_index('CodInst'), on='CodInst', how='inner')

df_resumo.reset_index(inplace=True)

#df_resumo.to_parquet(r"gs://group_one_bucket/arquivos_tratados/Inst_Fin_Resumo/resumo.parquet", index=False)

"""### EMPRÉSTIMOS"""

pd.concat([df1 ,df2])

folder_path = r"gs://group_one_bucket/arquivos_brutos/Emprestimos/planilhas_2021/"
file_list = gcsfs.GCSFileSystem(token=serviceAccount).glob(folder_path + "*.csv")
file_list = [os.path.join(r"gs://" + _) for _ in file_list]

df_emprestimos2021 = (pd.concat((pd.read_csv(f, sep=';', decimal=',') for f in file_list)))

df_emprestimos2021.to_parquet(r"gs://group_one_bucket/arquivos_brutos/Emprestimos_agrupado/emprestimos-2021-jan-ate-nov.parquet", index=False)

folder_path = r"gs://group_one_bucket/arquivos_brutos/Emprestimos/planilha_2020/"
file_list = gcsfs.GCSFileSystem(token=serviceAccount).glob(folder_path + "*.csv")
file_list = [os.path.join(r"gs://" + _) for _ in file_list]
df_emprestimos2020 = (pd.concat((pd.read_csv(f, sep=';',decimal=',') for f in file_list)))

df_emprestimos2020.to_parquet(r"gs://group_one_bucket/arquivos_brutos/Emprestimos_agrupado/emprestimos-2020.parquet", index=False)

folder_path = r"gs://group_one_bucket/arquivos_brutos/Emprestimos/planilha_2019/"
file_list = gcsfs.GCSFileSystem(token=serviceAccount).glob(folder_path + "*.csv")
file_list = [os.path.join(r"gs://" + _) for _ in file_list]
df_emprestimos2019 = (pd.concat((pd.read_csv(f, sep=';', decimal=',') for f in file_list)))

df_emprestimos2019.to_parquet(r"gs://group_one_bucket/arquivos_brutos/Emprestimos_agrupado/emprestimos_2019.parquet", index=False)

"""### QUADRO DE EMPRÉSTIMOS

2018
"""

agencias2018 = pd.read_excel('gs://group_one_bucket/arquivos_brutos/quadro_agencias/Quadro Agncias Dezembro 2018.xlsx', skiprows=6)

agencias2018.to_parquet('gs://group_one_bucket/arquivos_brutos/quadro_agencias_parquet/Qtd_agencias_por_banco_Dezembro_2018.parquet',index=False)

"""2019"""

col = ['UF','Total Municípios','Municípios com agência','Municípios sem agência com PA', 'Municípios sem agência sem PA e com PAE', 
       'Municípios sem agência sem PA e sem PAE','Municípios sem agência Total']

agencias2019 = pd.read_excel('gs://group_one_bucket/arquivos_brutos/quadro_agencias/Quadros agencias 2019.xlsx', 
                             sheet_name='quadro 4', skiprows=8, skipfooter=7,usecols='B,C,QL,QM,QN,QO,QP',header=None,names=col)

agencias2019.to_parquet('gs://group_one_bucket/arquivos_brutos/quadro_agencias_parquet/Qtd_agencias_Dezembro_2019.parquet',index=False)

"""2020"""

agencias2020 = pd.read_excel('gs://group_one_bucket/arquivos_brutos/quadro_agencias/Quadros agencias 2020.xlsx', 
                             sheet_name=4, skiprows=8, skipfooter=7,usecols='B,C,ST,SU,SV,SW,SX',header=None,names=col)

agencias2020.to_parquet('gs://group_one_bucket/arquivos_brutos/quadro_agencias_parquet/Qtd_agencias_Dezembro_2020.parquet',index=False)

"""2021"""

agencias2021 = pd.read_excel('gs://group_one_bucket/arquivos_brutos/quadro_agencias/Consolidade_geral_Janeiro2022.xlsx', 
                             sheet_name='quadro 4', skiprows=8, skipfooter=7,usecols='B,C,VB,VC,VD,VE,VF',header=None,names=col)

agencias2021.to_parquet('gs://group_one_bucket/arquivos_brutos/quadro_agencias_parquet/Qtd_agencias_Dezembro_2021.parquet',index=False)

agencias2018_2 = pd.read_excel('gs://group_one_bucket/arquivos_brutos/quadro_agencias/Consolidade_geral_Janeiro2022.xlsx', 
                             sheet_name='quadro 4', skiprows=8, skipfooter=7,usecols='B,C,OD,OE,OF,OG,OH',header=None,names=col)

agencias2018_2.to_parquet('gs://group_one_bucket/arquivos_brutos/quadro_agencias_parquet/Qtd_agencias_Dezembro_2018.parquet',index=False)

agencias2018_2['ano'] = 2018
agencias2021['ano'] = 2021
agencias2020['ano'] = 2020
agencias2019['ano'] = 2019

agencias = pd.concat([agencias2018_2,agencias2019,agencias2020,agencias2021])
agencias.to_parquet('gs://group_one_bucket/arquivos_brutos/quadro_agencias_parquet/Qtd_agencias_2018_a_2021.parquet',index=False)

"""### Quantidade de Transações por Canais de Acesso - Pagamento de Conta-Tributo e Transferência de Crédito (milhões).csv"""

pag_conta_transf_cred = pd.read_excel(
    'gs://group_one_bucket/arquivos_brutos/InstrumentosdePagamento-DadosEstatisticos2020/Quantidade de Transações por Canais de Acesso - Pagamento de Conta-Tributo e Transferência de Crédito (milhões).xlsx')
pag_conta_transf_cred = clean_columns(pag_conta_transf_cred)

pag_conta_transf_cred=pag_conta_transf_cred.add_prefix('ano_')
pag_conta_transf_cred.rename(columns={'ano_canal_de_acesso':'Canal_Acesso'},inplace=True)

pag_conta_transf_cred.to_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/pag_conta_transf_cred_pd.parquet', index=False)

"""### Quantidade de transações por Canal de Acesso e por Tipo de Operação (mil)


"""

qtd_trans_pcanal_e_op = [pd.read_excel(
    r'gs://group_one_bucket/arquivos_brutos/InstrumentosdePagamento-DadosEstatisticos2020/Quantidade de transações por Canal de Acesso e por Tipo de Operação (mil).xlsx', sheet_name=i) for i in range(6)]

"""#### Agência e Posto de Atendimento Tradicionais"""

ag_tradicionais = qtd_trans_pcanal_e_op[0].copy()

ag_tradicionais.fillna(0,inplace=True)

ag_tradicionais.rename(columns={'Agência e Posto de Atendimento Tradicionais':'agencias_tradicionais'}, inplace=True)

ag_tradicionais.columns = ag_tradicionais.columns.astype('str')

ag_tradicionais.to_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/Quantidade de transações por Canal de Acesso e por Tipo de Operação (mil)/ag_tradicionais_pmil_pd.parquet', index=False)

"""#### ATM"""

atm = qtd_trans_pcanal_e_op[1].copy()

atm.fillna(0,inplace=True)

atm.columns = atm.columns.astype('str')

atm.to_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/Quantidade de transações por Canal de Acesso e por Tipo de Operação (mil)/atm_pmil_pd.parquet',index=False)

"""#### Central de atendimento"""

central_atendimento = qtd_trans_pcanal_e_op[2].copy()

central_atendimento.fillna(0,inplace=True)

central_atendimento.columns = central_atendimento.columns.astype('str')

central_atendimento.rename(columns=lambda s: s.replace(' ', '_').lower(),inplace=True)

central_atendimento.to_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/Quantidade de transações por Canal de Acesso e por Tipo de Operação (mil)/central_atendimento_pmil_pd.parquet',index=False)

"""#### Correspondente no país"""

correspondentes = qtd_trans_pcanal_e_op[3].copy()

correspondentes.fillna(0,inplace=True)

correspondentes.columns = correspondentes.columns.astype('str')

correspondentes.rename(columns=lambda s: s.replace(' ', '_').lower(),inplace=True)

correspondentes.to_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/Quantidade de transações por Canal de Acesso e por Tipo de Operação (mil)/correspondentes_pmil_pd.parquet',index=False)

"""#### Internet, Home e Office Banking"""

net_home_ofc_banking = qtd_trans_pcanal_e_op[4].copy()

net_home_ofc_banking.fillna(0,inplace=True)

net_home_ofc_banking.columns = net_home_ofc_banking.columns.astype('str')

net_home_ofc_banking.rename(columns=lambda s: s.replace(' ', '_').lower(),inplace=True)

net_home_ofc_banking.to_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/Quantidade de transações por Canal de Acesso e por Tipo de Operação (mil)/net_home_ofc_banking_pmil_pd.parquet',index=False)

"""#### Telefone, celular e PDA"""

phone = qtd_trans_pcanal_e_op[5].copy()

phone.fillna(0,inplace=True)

phone.columns = phone.columns.astype('str')

phone.rename(columns=lambda s: s.replace(' ', '_').replace(',','').lower(),inplace=True)

phone.to_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/Quantidade de transações por Canal de Acesso e por Tipo de Operação (mil)/phone_pmil_pd.parquet',index=False)

"""### DISTRIBUIÇÃO TERMINAIS ATM"""

term_atm = pd.read_csv('gs://group_one_bucket/arquivos_brutos/InstrumentosdePagamento-DadosEstatisticos2020/Distribuição dos Terminais ATM por Unidade da Federação (Quantidade).csv', sep=';',thousands='.')

term_atm= term_atm.add_prefix('ano_')
term_atm.rename(columns={'ano_UF':'ESTADO'},inplace=True)
term_atm

term_atm.to_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/Distrib_Term_ATM_PD.parquet',index=False)

"""### CARTÕES DE CRÉDITO"""

debitos = pd.read_csv('gs://group_one_bucket/arquivos_brutos/InstrumentosdePagamento-DadosEstatisticos2020/Quantidade de Cartões de Débito.csv', sep=';',thousands='.',decimal=',')

debitos.Trimestre = debitos.Trimestre.apply(lambda x: roman.fromRoman(x))

debitos['Ano'] = debitos[['Ano','Trimestre']].astype('str').agg('-Q'.join,axis=1)

debitos.Ano = pd.PeriodIndex(debitos.Ano,freq='Q').to_timestamp(how='end')

debitos.Ano = debitos.Ano.dt.strftime('%Y-%m-%d')

debitos.to_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/qtd_de_cartoes_de_debitoTratado_pd.parquet')

"""### PROGRAMAS DE RECOMPENSAS"""

recompensas = pd.read_csv('gs://group_one_bucket/arquivos_brutos/InstrumentosdePagamento-DadosEstatisticos2020/Gastos com Programas de Recompensas pelos Emissores de Cartões.csv', sep=';', thousands='.', decimal=',')

recompensas.Ano = recompensas.Ano.apply(lambda x: pd.to_datetime('31-12-'+str(x)))

recompensas

"""### PRECATÓRIOS_2019 """

df_prec = pd.read_csv('https://storage.googleapis.com/group_one_bucket/arquivos_brutos/Precatorios/Prec_2019/precatorio_2019.csv', sep='\t',thousands='.', decimal=',')

df_prec.head()

df_prec.isnull().sum()

df_prec.columns

df_prec.drop([' .1', ' .2', ' '],axis=1,inplace=True)

df_prec.rename(columns={'Ente devedor':'ente_devedor', 'Esfera':'esfera', 'Montante pendente pagamento':'montante_pend_pagamento', 'Montante pago em 2019':'montante_pago_2019', 'Saldo apos pagamento':'saldo_pos_pagamento',
'Precatorios expedidos entre 2/07/2018 e 1/07/2019':'prec_exp_2_07_2018_ate_1_7_2019', 'Divida em 31/12/2019':'divida_31_12_2019'},inplace=True)

df_prec.head()

df_prec.columns

df_prec.shape

#Criação de um esquema em pandera
schema = pa.DataFrameSchema(
    columns = {
        "ente_devedor":pa.Column(pa.String),
        "esfera":pa.Column(pa.String),
        "montante_pend_pagamento":pa.Column(pa.Float),
        "montante_pago_2019":pa.Column(pa.Float),
        "saldo_pos_pagamento":pa.Column(pa.Float),
        "prec_exp_2_07_2018_ate_1_7_2019":pa.Column(pa.Float),
        "divida_31_12_2019":pa.Column(pa.Float),
    }
)

#Validação do esquema e confirmação de erro caso ocorra
try:
    schema.validate(df_prec, lazy=True)
except pa.errors.SchemaErrors as err:
    print("Schema errors and failure cases:")
    print(err.failure_cases)
    print("\nDataFrame object that failed validation:")
    print(err.data)

df_prec

df_prec.to_csv('gs://group_one_bucket/arquivos_tratados/Precatorios/precatorio_2019_tratado.csv', index=False)



"""### PRECATÓRIOS_2020 """

df_prec2 = pd.read_csv('https://storage.googleapis.com/group_one_bucket/arquivos_brutos/Precatorios/Prec_2020/precatorio_2020.csv', sep='\t', thousands='.', decimal=',')

df_prec2.head()

df_prec2.isnull().sum()

df_prec2.columns

df_prec2.drop([' .1', ' .2', ' '],axis=1,inplace=True)

df_prec2.rename(columns={'Ente devedor':'ente_devedor', 'Esfera':'esfera', 'Montante pendente pagamento':'montante_pend_pagamento', 'Montante pago em 2020':'montante_pago_2020', 'Saldo apos pagamento':'saldo_pos_pagamento',
'Precatorios expedidos entre 2/07/2019 e 1/07/2020':'prec_exp_2_07_2019_ate_1_7_2020', 'Divida em 31/12/2020':'divida_31_12_2020'},inplace=True)

df_prec2.head()

df_prec2.info()

schema2 = pa.DataFrameSchema(
    columns = {
        "ente_devedor":pa.Column(pa.String),
        "esfera":pa.Column(pa.String),
        "montante_pend_pagamento":pa.Column(pa.Float),
        "montante_pago_2020":pa.Column(pa.Float),
        "saldo_pos_pagamento":pa.Column(pa.Float),
        "prec_exp_2_07_2019_ate_1_7_2020":pa.Column(pa.Float),
        "divida_31_12_2020":pa.Column(pa.Float),
    }
)

try:
    schema2.validate(df_prec2, lazy=True)
except pa.errors.SchemaErrors as err:
    print("Schema errors and failure cases:")
    print(err.failure_cases)
    print("\nDataFrame object that failed validation:")
    print(err.data)

df_prec2

df_prec2.info()

df_prec2.to_csv('gs://group_one_bucket/arquivos_tratados/Precatorios/precatorio_2020_tratado.csv', index=False)

"""### PRECATÓRIOS TRATADOS"""

df_prec2019 = pd.read_csv('gs://group_one_bucket/arquivos_tratados/Precatorios/precatorio_2019_tratado.csv')

data_divida = df_prec2019.apply(lambda x: pd.to_datetime('31-12-2019',format='%d-%m-%Y'),axis=1)

df_prec2019.insert(df_prec2019.columns.get_loc('divida_31_12_2019')+1,'data_divida',data_divida)

periodo_expedicao1 = df_prec2019.apply(lambda x: pd.to_datetime('02-07-2018'),axis=1)

periodo_expedicao2 = df_prec2019.apply(lambda x: pd.to_datetime('01-07-2019'),axis=1)

df_prec2019.insert(df_prec2019.columns.get_loc('prec_exp_2_07_2018_ate_1_7_2019')+1,'fim_periodo_expedicao',periodo_expedicao2)

df_prec2019.insert(df_prec2019.columns.get_loc('prec_exp_2_07_2018_ate_1_7_2019')+1,'ini_periodo_expedicao',periodo_expedicao1)

df_prec2019.rename({'prec_exp_2_07_2018_ate_1_7_2019':'precatorios_expedidos','divida_31_12_2019': 'valor_divida','montante_pago_2019':'montante_pago'}, axis=1, inplace=True)

df_prec2019.head()

df_prec2020 = pd.read_csv('gs://group_one_bucket/arquivos_tratados/Precatorios/precatorio_2020_tratado.csv')

data_divida = df_prec2020.apply(lambda x: pd.to_datetime('31-12-2020',format='%d-%m-%Y'),axis=1)

df_prec2020.insert(df_prec2020.columns.get_loc('divida_31_12_2020')+1,'data_divida',data_divida)

periodo_expedicao1 = df_prec2020.apply(lambda x: pd.to_datetime('02-07-2019'),axis=1)

periodo_expedicao2 = df_prec2020.apply(lambda x: pd.to_datetime('01/07/2020'),axis=1)

df_prec2020.insert(df_prec2020.columns.get_loc('prec_exp_2_07_2019_ate_1_7_2020')+1,'fim_periodo_expedicao',periodo_expedicao2)

df_prec2020.insert(df_prec2020.columns.get_loc('prec_exp_2_07_2019_ate_1_7_2020')+1,'ini_periodo_expedicao',periodo_expedicao1)

df_prec2020.rename({'prec_exp_2_07_2019_ate_1_7_2020':'precatorios_expedidos','divida_31_12_2020': 'valor_divida','montante_pago_2020':'montante_pago'}, axis=1, inplace=True)

df_prec2020.head()

df_prec = (pd.concat([df_prec2019,df_prec2020]))

df_prec.head()

df_prec.to_parquet(r"gs://group_one_bucket/arquivos_tratados/Precatorios/precatorio_tratado.parquet", index=False)

"""### **Precatorios_PD**"""

df_path = "gs://group_one_bucket/arquivos_tratados/Precatorios/precatorio_tratado.parquet"

df_prec = pd.read_parquet(df_path, engine='auto', columns=None, storage_options=None, use_nullable_dtypes=False)

pandas_profiling.ProfileReport(df_prec,minimal=True)

df_prec.head(5)

df_prec.info()

print(df_prec.describe())

df_prec[df_prec.duplicated()].shape[0]

df_prec.isna().sum()

df_prec.to_parquet(r"gs://group_one_bucket/arquivos_tratados/Precatorios/Precatorio_PD.parquet", index=False, storage_options={'token':serviceAccount})

"""### **Endivid_fami_PD**"""

df_path = "gs://group_one_bucket/arquivos_tratados/Outros_Tratados/endividamento_das_familias_tratados.csv"

df_endf = pd.read_csv(df_path,sep=',', thousands='.')
df_endf.tail()

pandas_profiling.ProfileReport(df_endf,minimal=True)

df_endf.info()



df_endf = df_endf["Data"].fillna("0000/00/00", inplace = True)

df_endf = df_endf.replace('-','0.00')

df_endf['inad_cart_cred_pj_tot_porc'] = df_endf['inad_cart_cred_pj_tot_porc'].str.replace(r',', '.')

df_endf['inad_cart_cred_pf_tot_porc'] = df_endf['inad_cart_cred_pf_tot_porc'].str.replace(r',', '.')

df_endf['comp_renda_fam_jur_div_sfn_rndbf_perc'] = df_endf['comp_renda_fam_jur_div_sfn_rndbf_perc'].str.replace(r',', '.')

df_endf['comp_renda_fam_amort_div_sfn_rndbf_perc'] = df_endf['comp_renda_fam_amort_div_sfn_rndbf_perc'].str.replace(r',', '.')

df_endf['end_fam_sfn_exc_cred_hab_rel_renda_acu_12_mes_rndbf_perc'] = df_endf['end_fam_sfn_exc_cred_hab_rel_renda_acu_12_mes_rndbf_perc'].str.replace(r',', '.')

df_endf['comp_renda_fam_serv_sfn_exc_cred_hab_rndbf_perc'] = df_endf['comp_renda_fam_serv_sfn_exc_cred_hab_rndbf_perc'].str.replace(r',', '.')

df_endf['Data'] = pd.to_datetime(df_endf['Data'])

df_endf['Data'] = pd.to_datetime(df_endf['Data'], format='%M/%y')
df_endf['Data'] = pd.to_datetime(df_endf['Data']).dt.normalize()



df_endf['inad_cart_cred_tot_porc'] = pd.to_numeric(df_endf['inad_cart_cred_tot_porc'])

df_endf.iloc[74]

df_endf.head()

df_endf.info()

df_endf.rename(columns={'Data': 'Periodo'}, inplace = True)

columns = ['inad_cart_cred_tot_porc', 'inad_cart_cred_pj_tot_porc', 'inad_cart_cred_pf_tot_porc', 'comp_renda_fam_jur_div_sfn_rndbf_perc', 'comp_renda_fam_serv_sfn_rndbf_perc', 'comp_renda_fam_serv_sfn_exc_cred_hab_rndbf_perc', 'comp_renda_fam_amort_div_sfn_rndbf_perc', 'end_fam_sfn_renda_12_mes_perc', 'end_fam_sfn_exc_cred_hab_rel_renda_acu_12_mes_rndbf_perc'] 

df_endf[columns] = df_endf[columns].apply(lambda x: x.str.replace(',', '.').astype('float'))

df_endf.to_parquet(r'gs://group_one_bucket/arquivos_tratados/Outros_Tratados/endividamento_das_familias_PD.parquet', index=False, storage_options={'token':serviceAccount})

"""### Quadro de **Agências_PD**"""

df_path = "gs://group_one_bucket/arquivos_brutos/quadro_agencias_parquet/Qtd_agencias_2018_a_2021.parquet"

df_qdag = pd.read_parquet(df_path, engine='auto', columns=None, storage_options=None, use_nullable_dtypes=False)

df_qdag.head()

pandas_profiling.ProfileReport(df_qdag,minimal=True)

df_qdag.info()

print(df_qdag.describe())

df_qdag.to_parquet(r"gs://group_one_bucket/arquivos_brutos/quadro_agencias_parquet/QuadroAgencias_PD.parquet", index=False, storage_options={'token':serviceAccount})

"""## MYSQL

#### tratamento minimo necessário para carregar tabelas no sql
"""

b3_2019 = pd.read_csv("gs://group_one_bucket/arquivos_brutos/B3_bancos_Bruto/B32019.csv",header=None,sep=';',low_memory=False)

b3_2020 = pd.read_csv("gs://group_one_bucket/arquivos_brutos/B3_bancos_Bruto/B32020.csv",header=None,sep=';',low_memory=False)

b3_2022 = pd.read_csv("gs://group_one_bucket/arquivos_brutos/B3_bancos_Bruto/B32022.csv",header=None,sep=';',low_memory=False)

b3_2021 = pd.read_csv("gs://group_one_bucket/arquivos_brutos/B3_bancos_Bruto/B3_2021.csv",sep=',',low_memory=False)

dre_sql = dr_all.copy()

dre_sql.rename(columns=lambda x: x.split('\n')[0],inplace=True)
dre_sql.rename(columns=lambda x: x.strip().replace(' ','_'),inplace=True)
dre_sql.columns.values[-5] = 'Receitas_de_Operações_de_Câmbio'
dre_sql.columns.values[-4] = 'Despesas_de_Operações_de_Câmbio'

resumo_sql = df_resumo.copy()
resumo_sql.rename(columns=lambda x: x.split('\n')[0],inplace=True)
resumo_sql.rename(columns=lambda x: x.strip().replace(' ','_'),inplace=True)
resumo_sql.rename(columns={
    'Passivo_Circulante_e_Exigível_a_Longo_Prazo_e_Resultados_de_Exercícios_Futuros':
    'Passivo_Circ_Longo_Prazo_e_Result_Exer_Futuros'},
    inplace=True)

#emprestimos = pd.read_parquet('gs://group_one_bucket/arquivos_brutos/Emprestimos_agrupado/emprestimos-2021-jan-ate-nov.parquet')

listagem_nome_IF = pd.read_csv('gs://group_one_bucket/arquivos_brutos/listagem_bancos.csv')

fs = gcsfs.GCSFileSystem(token=serviceAccount)
with fs.open('gs://group_one_bucket/arquivos_brutos/Pix_TED_CHQ/arquivos_brutos_PIX liquidados no SPI (1).json', 'rb') as f:
  j = json.loads(f.read())
  pix = pd.DataFrame(j['value'])

pix.Data = pd.to_datetime(pix.Data)

ted = pd.read_csv('gs://group_one_bucket/arquivos_brutos/Pix_TED_CHQ/arquivos_brutos_TED que envolve clientes - Evolução Diária - TED que envolve clientes - Evolução Diária.csv', sep=',')

fs = gcsfs.GCSFileSystem(token=serviceAccount)
with fs.open('gs://group_one_bucket/arquivos_brutos/Pix_TED_CHQ/arquivos_brutos_Quantidade de Cheques Trocados no Pais.json', 'rb') as f:
  j = json.loads(f.read())
  cheque = pd.DataFrame(j['value'])

precatorio2019 = pd.read_csv('gs://group_one_bucket/arquivos_brutos/Precatorios/Prec_2019/precatorio_2019.csv', sep='\t',thousands='.',decimal=',')
precatorio2019.drop([' ', ' .1', ' .2'],axis=1,inplace=True)

precatorio2019

precatorio2020 = pd.read_csv('gs://group_one_bucket/arquivos_brutos/Precatorios/Prec_2020/precatorio_2020.csv', sep='\t',thousands='.',decimal=',')
precatorio2020.drop([' ', ' .1', ' .2'],axis=1,inplace=True)

precatorio2020

endiv_familias = pd.read_csv('gs://group_one_bucket/arquivos_brutos/Pix_TED_CHQ/arquivos_brutos_endividamento das familias.csv',sep=';',encoding='latin',decimal=',')
endiv_familias = clean_columns(endiv_familias)
col = endiv_familias.columns.to_list()
novo =['data',
 'inad_cart_cred_total_%',
 'inad_cart_de_cred_pj_%',
 'inad_cart_cred_pf_%',
 'compr_renda_juros_divida_sfn_com_aj_saz_%',
 'compr_renda_serv_div_sfn_com_aj_saz_%',
 'compr_renda_serv_div_sfn_exceto_cred_habit_com_aj_saz_%',
 'compr_renda_com_amort_div_com_sfn_com_aj_saz_%',
 'endiv_com_sfn_em_rel_renda_acum_ult_doze_meses_%',
 'endiv_sfn_exceto_cred_habit_em_rel_renda_ult_12_meses_%']
cols = dict(zip(col,novo))
endiv_familias.rename(columns=cols, inplace=True)

quadro_agencias = pd.read_parquet('gs://group_one_bucket/arquivos_brutos/quadro_agencias_parquet/Qtd_agencias_2018_a_2021.parquet')

agencias_por_banco = pd.read_parquet('gs://group_one_bucket/arquivos_brutos/quadro_agencias_parquet/Qtd_agencias_por_banco_Dezembro_2018.parquet')
agencias_por_banco = agencias_por_banco.iloc[:,1:]

agencias_por_banco

atm = pd.read_csv(r"gs://group_one_bucket/arquivos_brutos/InstrumentosdePagamento-DadosEstatisticos2020/Distribuição dos Terminais ATM por Unidade da Federação (Quantidade).csv", sep=';')

programa_recompensas = pd.read_csv("gs://group_one_bucket/arquivos_brutos/InstrumentosdePagamento-DadosEstatisticos2020/Gastos com Programas de Recompensas pelos Emissores de Cartões.csv", sep=';')
programa_recompensas =  clean_columns(programa_recompensas)

carteira_credito = pd.read_parquet('gs://group_one_bucket/arquivos_brutos/carteira_credito_bancos/carteira_creditos.parquet')

col = b3_2021.columns.to_list()

col_dict = dict(zip(b3_2019.columns.to_list(),col))
b3_2019.rename(columns=col_dict,inplace=True)

col_dict = dict(zip(b3_2020.columns.to_list(),col))
b3_2020.rename(columns=col_dict,inplace=True)

col_dict = dict(zip(b3_2022.columns.to_list(),col))
b3_2022.rename(columns=col_dict,inplace=True)

"""#### funcao para carregar datasets no mysql"""

def dataframe_tomysql(dataframe, nome_tabela: str, insercoes_por_vez: int or None = None) -> None:
  '''
  dataframe: pandas dataframe
  nome_tabela: string com nome da tabela formatado no padrao sql
  '''
  from sqlalchemy import create_engine
  ip = '35.237.155.249'
  database = 'projeto_final'
  user = 'root'
  senha = '1234567890'

  sqlEngine = create_engine(f'mysql+pymysql://{user}:{senha}@{ip}/{database}', 
                            pool_recycle=3600,
                            pool_pre_ping=True)

  try:
    result = dataframe.to_sql(nome_tabela, sqlEngine, index=False, if_exists='append', chunksize=insercoes_por_vez, method='multi')
  except Exception as ex:   
    print(ex)
  else:
    print(f"Tabela {nome_tabela} criada com sucesso. {result}")

"""#### carregar datasets no mysql"""

dataframe_tomysql(dre_sql, 'dre_instituicoes_financeiras')

dataframe_tomysql(resumo_sql, 'resumo_financeiro_if')

dataframe_tomysql(listagem_nome_IF,'nomes_if',1000)

dataframe_tomysql(b3_2019,'bolsa_valores_b3',1000)

dataframe_tomysql(b3_2020, 'bolsa_valores_2020',1000)

dataframe_tomysql(b3_2021,'bolsa_valores_2021',1000)

dataframe_tomysql(b3_2022,'bolsa_valores_2022',1000)

#dataframe_tomysql(emprestimos,'emprestimos',1000)

dataframe_tomysql(pix,'pix',1000)

dataframe_tomysql(ted,'ted',1000)

dataframe_tomysql(cheque,'cheque',1000)

dataframe_tomysql(precatorio2019,'precatorio2019',1000)

dataframe_tomysql(endiv_familias,'endiv_familias',1000)

dataframe_tomysql(precatorio2020,'precatorio2020',1000)

dataframe_tomysql(quadro_agencias,'quadro_agencias',1000)

dataframe_tomysql(agencias_por_banco,'agencias_por_banco',1000)

dataframe_tomysql(term_atm,'dist_ATM_por_UF',1000)

dataframe_tomysql(programa_recompensas,'programa_recompensas',1000)

dataframe_tomysql(carteira_credito,'carteira_de_creditos_bancos',1000)

dataframe_tomysql(atm,'qtd_transacoes_de_atm_por_canal',1000)

dataframe_tomysql(ag_tradicionais,'qtd_transacoes_de_agencias_por_canal',1000)

dataframe_tomysql(central_atendimento,'qtd_transacaoes_de_ca_por_canal',1000)

dataframe_tomysql(correspondentes,'qtd_transacoes_de_correspondentes_por_canal',1000)

dataframe_tomysql(net_home_ofc_banking,'qtd_transacoes_remota_por_canal',1000)

dataframe_tomysql(phone,'qtd_transacoes_de_tele_por_canal',1000)

dataframe_tomysql(pag_conta_transf_cred,'qtd_transac__pag_de_conta_e_transf_de_cred',1000)

dataframe_tomysql(debitos,'emissao_cartao_creditos', 1000)

dataframe_tomysql(recompensas,'programas_de_recompesa', 1000)

df_creditos = pd.read_csv('gs://group_one_bucket/arquivos_brutos/InstrumentosdePagamento-DadosEstatisticos2020/Quantidade de Cartões de Crédito (estoque no final do trimestre).csv',sep=';',thousands='.')
dataframe_tomysql(df_creditos,'emissao_cartao_creditos', 1000)

"""##Acesso Mongo
Os datasets serão enviados ao mongo via colab

Colocando dados tratados no mongo

### configs
"""

def test_client(client: MongoClient) -> None:
  try:
    print(client.server_info())
  except Exception as err:
    print("Falha na conexão com o server", err)

#Acessando o mongo client
client = MongoClient(r"mongodb+srv://soulcode:a1b2c3@projeto-final.5v1wl.mongodb.net/test?retryWrites=true&w=majority", serverSelectionTimeoutMS=5000)
test_client(client)

client2 = MongoClient(r'mongodb+srv://soulcode:a1b2c3@cluster0.hi0t8.mongodb.net/myFirstDatabase?retryWrites=true&w=majority')
test_client(client2)

client3 = MongoClient('mongodb+srv://soulcode:a1b2c3@cluster0.isyzu.mongodb.net/myFirstDatabase?retryWrites=true&w=majority')
test_client(client3)

client4 = MongoClient('mongodb+srv://soulcode:a1b2c3@cluster0.vpegy.mongodb.net/admin?retryWrites=true&w=majority', retryWrites=True, serverSelectionTimeoutMS=5000)
test_client(client4)

#Acessando a database
db = client["datasets"]

database = client2['datasets']

db3 = client3['datasets']

db4 = client4['datasets']

"""### Otimizador de variaveis"""

from typing import List


def optimize_floats(df: pd.DataFrame) -> pd.DataFrame:
    floats = df.select_dtypes(include=['float64']).columns.tolist()
    df[floats] = df[floats].apply(pd.to_numeric, downcast='float')
    return df


def optimize_ints(df: pd.DataFrame) -> pd.DataFrame:
    ints = df.select_dtypes(include=['int64']).columns.tolist()
    df[ints] = df[ints].apply(pd.to_numeric, downcast='integer')
    return df


def optimize_objects(df: pd.DataFrame, datetime_features: List[str]) -> pd.DataFrame:
    for col in df.select_dtypes(include=['object']):
        if col not in datetime_features:
            if not (type(df[col][0])==list):
                num_unique_values = len(df[col].unique())
                num_total_values = len(df[col])
                if float(num_unique_values) / num_total_values < 0.5:
                    df[col] = df[col].astype('category')
        else:
            df[col] = pd.to_datetime(df[col])
    return df



def optimize(df: pd.DataFrame, datetime_features: List[str] = []) -> pd.DataFrame:
    return optimize_floats(optimize_ints(optimize_objects(df, datetime_features)))

"""### Carregar DRE"""

#Carregando dados
colecao = db.dre
dre = pd.read_parquet('gs://group_one_bucket/arquivos_tratados/Inst_Fin_Demonstrativo/dre_pd.parquet')

# campo de tempo no datetime estavá nulo e mongo não permite isso, corrigimos adicionando o menor tempo possível ao campo, que no caso deve ser tudo zero
dre.AnoMes = dre.AnoMes.apply(lambda x: datetime.combine(x, time.min))

colecao.drop()

df_mongo= dre.to_dict('records')
colecao.insert_many(df_mongo).acknowledged

"""### Carregar RESUMO FINANCEIRO"""

colecao = db.resumo_financeiro
resumo = pd.read_parquet('gs://group_one_bucket/arquivos_tratados/Inst_Fin_Resumo/resumo_py.parquet/part-00000-2c55a475-0898-41d8-a8a4-2970219dcce8-c000.snappy.parquet')

# campo de tempo no datetime estavá nulo e mongo não permite isso, corrigimos adicionando o menor tempo possível ao campo, que no caso deve ser tudo zero
resumo.AnoMes = resumo.AnoMes.apply(lambda x: datetime.combine(x, time.min))

df_mongo = resumo.to_dict('records')
colecao.insert_many(df_mongo).acknowledged

"""### Carregar Instrumentos de pagamentos"""

colecao = db.terminais_atm
terminais_atm = pd.read_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/Distrib_Term_ATM_PD.parquet')

colecao.drop()

df_mongo= terminais_atm.to_dict('records')
colecao.insert_many(df_mongo).acknowledged

"""### Cartoes de creditos emitidos"""

colecao = db.cartoes_credito
cartoes_credito = pd.read_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/Qtd_Cartao_Cred_PD.parquet')

colecao.drop()

df_mongo= cartoes_credito.to_dict('records')
colecao.insert_many(df_mongo).acknowledged

"""### Cartões de debitos emitidos"""

cartoes_debito = pd.read_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/qtd_de_cartoes_de_debitoTratado_pd.parquet')
colecao = db.cartoes_debito

colecao.drop()

df_mongo= cartoes_debito.to_dict('records')
colecao.insert_many(df_mongo,).acknowledged

"""### Transações por canal de acesso em pagamentos de conta, tributos e transferências"""

transacoes_canal = pd.read_parquet('gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/pag_conta_transf_cred_pd.parquet')
colecao = db.transacoes_por_canal_acesso_em_pag_e_trib_transf

colecao.drop()

df_mongo= transacoes_canal.to_dict('records')
colecao.insert_many(df_mongo,).acknowledged

"""### Transações por canal e por tipo de operação"""

transacoes_oper = pd.read_parquet(r'gs://group_one_bucket/arquivos_tratados/Instrumentos_pagamentos2/Quantidade de transações por Canal de Acesso e por Tipo de Operação (mil)/Qnt_trans_canal_acesso_tipo_op_mil_pd.parquet')
colecao = db.transacoes_por_canal_e_operacoes_em_mil

colecao.drop()

df_mongo= transacoes_oper.to_dict('records')
colecao.insert_many(df_mongo).acknowledged

"""### Endividamento das famílias"""

endividamento = pd.read_parquet('gs://group_one_bucket/arquivos_tratados/Outros_Tratados/endividamento_das_familias_PD.parquet')
colecao = db.endividamentos_familias

colecao.drop()

df_mongo = endividamento.to_dict('records')
colecao.insert_many(df_mongo,).acknowledged

"""### B3 Bancos"""

colecao = db.b3_bancos
b3_bancos = pd.read_parquet('gs://group_one_bucket/arquivos_tratados/B3_Bancos_Tratado/B3_bancos_new_PD.parquet')

colecao.drop()
df_mongo = b3_bancos.to_dict('records')
colecao.insert_many(df_mongo).acknowledged

"""### Precatorios"""

colecao = db4.precatorios
precatorios = pd.read_parquet('gs://group_one_bucket/arquivos_tratados/Precatorios/Precatorio_PD.parquet')

colecao.drop()
df_mongo = precatorios.to_dict('records')
colecao.insert_many(df_mongo).acknowledged

"""# pipeline"""

pip install apache_beam[interactive]

pip install apache-beam[gcp]

pip install beam-mysql-connector

from pandas.core.frame import DataFrame
import pandas as pd
import apache_beam as beam
import json
import gcsfs
import os
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.options.pipeline_options import SetupOptions
import argparse, logging

project_id = 'group-one-pfinal-soulcode'
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = serviceAccount

parser = argparse.ArgumentParser() #add argumento
# parser.add_argument('--my-arg', help='description')
parser.add_argument(
    '--input-file',
    default='gs://group_one_bucket/arquivos_brutos/Pix_TED_CHQ/arquivos_brutos_PIX liquidados no SPI (1).json',
    help='O caminho do arquivo para processar.')
parser.add_argument('--table', required=True, help='Nome da tabela a ser criada')
parser.add_argument('--table', required=True, help='Nome da tabela a ser criada')
args, beam_args = parser.parse_known_args()

# Criando pipiline options.
# especificando o dataflow
# projeto, nome do trabalho, lcalização de pastas temporárias, região.
beam_options = PipelineOptions(
    beam_args,
    runner='DataflowRunner',
    project=project_id,
    job_name='mysql-ingestion-with-pandas-for-json',
    temp_location='gs://group_one_bucket/arquivos_brutos/stage',
    template_location='gs://group_one_bucket/models/modelo_sql_ingestion',
    region='us-east1')

def to_sql(record, nome_tabela):
  '''
  record: row do frame
  nome_tabela: Nome da tabela a ser criada
  '''
  from sqlalchemy import create_engine
  ip = '35.237.155.249'
  database = 'projeto_final'
  user = 'root'
  senha = '1234567890'


  sqlEngine = create_engine(f'mysql+pymysql://{user}:{senha}@{ip}/{database}', 
                            pool_recycle=3600,
                            pool_pre_ping=True)
  
  pd.DataFrame(record).to_sql(nome_tabela, sqlEngine, index=False, if_exists='append', chunksize=1000, method='multi')
  logging.info(f"Tabela {nome_tabela} criada com sucesso.")


'''parser = argparse.ArgumentParser()
known_args, pipeline_args = parser.parse_known_args(argv)

pipeline_options = PipelineOptions(pipeline_args)
pipeline_options.view_as(SetupOptions).save_main_session = True'''
'''options = {
    'project': project_id,
    'runner': 'DataflowRunner',
    'region': 'us-east1',
    'staging_location': 'gs://group_one_bucket/arquivos_brutos/stage',
    'temp_location': 'gs://group_one_bucket/arquivos_brutos/stage',
    'template_location': 'gs://group_one_bucket/models/modelo_sql_ingestion',
    'save_main_session': True,
    'token': '/tmp/key.json',
    'path' : 'gs://group_one_bucket/arquivos_brutos/Pix_TED_CHQ/arquivos_brutos_PIX liquidados no SPI (1).json',
    'nome_tabela': 'pix'
}'''

with beam.Pipeline(options=beam_options) as pipeline:
  #pipeline_options = PipelineOptions.from_dictionary(options)

  fs = gcsfs.GCSFileSystem(project=pipeline.options.project, token=)
  with fs.open(pipeline.options.input, 'rb') as f:
    dict = json.loads(f.read())

    pcollection_entrada = (
      pipeline | 'Ler do arquivo' >> beam.Create(dict['value'])
      )

    sql = (
        pcollection_entrada
        # Cria um elemento com todos dados do arquivo em uma PCollection
        #| 'Uniton' >> beam.Create([None])
        |'Enviar para sql' >> beam.FlatMap(lambda _, x : to_sql(x, pipeline.options.table), x = beam.pvalue.AsIter(pcollection_entrada))
        #|'Log' >> beam.io.WriteToText(r'gs://group_one_bucket/logs_flow/log_sql.txt')
    )

'''pipeline = beam.Pipeline(options=pipeline_options)

pcollection_entrada = (
    pipeline | 'Ler do arquivo' >> beam.Create(dict['value'])
    )

sql = (
    pcollection_entrada
    # Cria um elemento com todos dados do arquivo em uma PCollection
    #| 'Uniton' >> beam.Create([None])
    |'Enviar para sql' >> beam.FlatMap(lambda _, x : to_sql(x, options['table-name']), x = beam.pvalue.AsIter(pcollection_entrada))
    #|'Log' >> beam.io.WriteToText(r'gs://group_one_bucket/logs_flow/log_sql.txt')
)'''

if __name__ == '__main__':
  resultado = pipeline.run()
  resultado.wait_until_finish()
