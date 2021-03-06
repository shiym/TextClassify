# -*- coding: utf-8 -*-
"""
Created on Mon Sep  3 13:55:53 2018
# 用gensim训练出来的doc2vec对文本进行分类:
@author: Vino
"""
import pandas as pd
import os
from sklearn.externals import joblib
from gensim import corpora,models
from collections import defaultdict
from Parameter import ProjectPath
from utils import train_classify,write_data,save_prob_file,logging

class MLTextClassify(ProjectPath):
    '''
    通过手工提取特征,然后利用Machine Learning对文本进行分类...
    '''
    def __init__(self,column,classify_mode,feature_mode,feature_num,raw_corpus):
        ProjectPath.__init__(self)
        self.classify_mode = classify_mode #option,['LR','SVC','lightgbm']
        self.column = column # option ['word_seg','article']
        self.feature_mode = feature_mode # option ['lsi','lda','tfidf']
        self.feature_num = feature_num #提取特征的维度
        self.feature_model_file = os.path.join(self.model_dir,"{}_{}_{}d.model".format(self.feature_mode,self.column,self.feature_num))#提取特征模型的文件
        self.feature_data_file = os.path.join(self.model_dir,"{}_{}_{}d.dat".format(self.feature_mode,self.column,self.feature_num))#抽取特征的保存文件(使用joblib)
        self.dict_file = os.path.join(self.model_dir, "{}.dict".format(column)) #使用gensim格式的字典文件
        self.corpus_file = os.path.join(self.model_dir, "{}.corpus".format(column)) #使用gensim格式的语料文件
        self.testSet = pd.read_csv(self.test_file) #预测集的文件DataFrame
        self.feature_test_X = None #人工抽取预测集后的特征文件
        self.trainSet = pd.read_csv(self.train_file) #训练集的数据DataFrame
        self.corpus = None
        self.dictionary = None
        self.classify_model = None
        self.feature_model = None
        self.raw_corpus = raw_corpus

    def load_data(self):
        '''
        通过对输入的corpus进行加工,得到gensim能用的dictionary和corpus,用于后续训练lda模型
        加载数据的训练集trainSet和预测集testSet
        :return: no
        '''
        if os.path.exists(self.dict_file) == True:
            logging.info("wait load corpus and dictionary ...")
            dictionary = corpora.Dictionary.load(self.dict_file)
            corpus = corpora.MmCorpus(self.corpus_file)
            self.corpus = corpus
            self.dictionary = dictionary
        else:
            logging.info("please wait create corpus and dictionary...")
            texts = [[word for word in document.split(' ')] for document in self.raw_corpus]
            frequency = defaultdict(int)
            for text in texts:
                for token in text:
                    frequency[token] += 1
            texts = [[token for token in text if frequency[token] > 5] for text in texts]
            dictionary = corpora.Dictionary(texts)
            corpus = [dictionary.doc2bow(text) for text in texts]
            dictionary.save(self.dict_file)
            corpora.MmCorpus.serialize(self.corpus_file,corpus)
            self.corpus = corpus
            self.dictionary = dictionary

    def train_feature_model(self):
        '''
        训练特征提取模型,或者加载特征提取模型
        :return: lda模型
        '''
        if self.feature_mode=='lda':
            if os.path.exists(self.feature_model_file):
                logging.info("load LDA model...")
                lda = models.LdaModel.load(self.feature_model_file)
                self.feature_model=lda
            else:
                lda = models.LdaModel(self.corpus, id2word=self.dictionary, num_topics=self.feature_num, update_every=0,passes=20)
                lda.save(self.feature_model_file)
                self.feature_model = lda
        elif self.feature_mode=='lsi':
            if os.path.exists(self.feature_model_file):
                logging.info("load LSI model...")
                lsi = models.LsiModel.load(self.feature_model_file)
                self.feature_model=lsi
            else:
                lsi = models.LsiModel(self.corpus, id2word=self.dictionary, num_topics=self.feature_num)
                lsi.save(self.feature_model_file)
                self.feature_model = lsi
        return True

    def _get_feature(self,corpus):
        '''
        :param 对任意的list类型的语料,提取对应模型的特征,用于训练分类模型
        :return: numpy或scipy的features
        '''
        from gensim.matutils import corpus2dense
        texts = [[word for word in doc.split(' ')]for doc in corpus]
        doc = [self.dictionary.doc2bow(text) for text in texts]
        vec = self.feature_model[doc]
        features = corpus2dense(vec,self.feature_num).T
        return features

    def train_classify_model(self):
        '''
        通过机器学习,训练分类模型
        :return:
        '''
        dataX,dataY = self._get_feature(self.trainSet[self.column].tolist()),(self.trainSet['class']-1).tolist()
        self.classify_model,self.best_score = train_classify(dataX,dataY,self.classify_mode)

    def save_features(self):
        '''
        保存对训练集和预测集提取的features用于后续调节分类模型或者特征的concat操作
        :return:
        '''
        if os.path.exists(self.feature_data_file):
            (trainX,testX)=joblib.load(self.feature_data_file)
            self.feature_test_X = testX
        else:
            trainX,testX = self._get_feature(self.trainSet[self.column].tolist()),self._get_feature(self.testSet[self.column].tolist())
            joblib.dump((trainX,testX),self.feature_data_file)
            self.feature_test_X = testX

    def predict(self):
        '''
        将预测集的数据通过分类器进行预测，并得到类别结果和概率
        :return:
        '''
        y_pred = self.classify_model.predict(self.feature_test_X)
        y_prob = self.classify_model.predict_proba(self.feature_test_X)
        logging.info("测试数据预测完成,开始写入结果文件...")
        result_file = os.path.join(self.result_dir,"{}_{}_{}_{}d_{:.3f}.csv".format(self.feature_mode,self.column,self.classify_mode,self.feature_num,self.best_score))
        result_prob_file = os.path.join(self.result_dir,"{}_{}_{}_{}d_{:.3f}_prob.csv".format(self.feature_mode,self.column,self.classify_mode,self.feature_num,self.best_score))
        result_string = ['id,class\n']
        for id,pred in enumerate(y_pred):
            string = "{},{}\n".format(id,pred+1)
            result_string.append(string)
        write_data(''.join(result_string),result_file)
        save_prob_file(y_prob,result_prob_file)
        logging.info("数据提交完毕,请查看{}...".format(self.result_dir))
        return True

    def run(self):
        logging.info("加载数据...")
        self.load_data()
        logging.info("训练 {} 特征抽取模型...".format(self.feature_mode))
        self.train_feature_model()
        self.save_features()
        logging.info("训练 {} 分类模型...".format(self.classify_mode))
        self.train_classify_model()
        logging .info("对预测集进行预测...")
        self.predict()

if __name__ == "__main__":
    column = 'word_seg'
    classify_mode = 'LR'
    feature_mode = "lsi"
    feature_num = 20
    df1 = pd.read_csv('../data/train_set.csv')
    df2 = pd.read_csv('../data/test_set.csv')
    column = 'word_seg'
    text1 = set(df1[column].tolist())
    text2 = set(df2[column].tolist())
    raw_corpus = list(text1 | text2)
    logging.info("raw_corpus's line :{}".format(len(raw_corpus)))
    test = MLTextClassify(column,classify_mode,feature_mode,feature_num,raw_corpus)
    test.run()
