import numpy as np
import threading
import os
import sklearn
from sklearn import cross_validation
import matplotlib.pyplot as plt
import itertools
from functools import partial
import warnings

import tensorflow as tf
import keras
from keras.models import Sequential, Model
from keras.layers import Input, Dense, TimeDistributed, merge, Lambda
from keras.layers.core import *
from keras.layers.convolutional import *
from keras.layers.recurrent import *
from keras.regularizers import l2,l1
from keras.layers.normalization import BatchNormalization
from keras import backend as K
from keras.layers.core import Reshape
from keras.activations import relu
from keras.utils import np_utils
from keras.optimizers import RMSprop,SGD,Adam
from keras.callbacks import ModelCheckpoint, ReduceLROnPlateau

import get_data
import train
warnings.filterwarnings("ignore")

# Path to the directories of features and labels
feature_dir = '/home/ye/Works/pain'
label_dir = '/home/ye/Works/pain/Sequence_Labels'
feature_name = 'feature_from_verification_model.mat'
label_name = 'OPR'

#######################################################################
def max_filter(x):
    # Max over the best filter score (like ICRA paper)
    max_values = K.max(x, 2, keepdims=True)
    max_flag = tf.greater_equal(x, max_values)
    out = x * tf.cast(max_flag, tf.float32)
    return out

def channel_normalization(x):
    # Normalize by the highest activation
    max_values = K.max(K.abs(x), 2, keepdims=True)+1e-5
    out = x / max_values
    return out

def WaveNet_activation(x):
    tanh_out = Activation('tanh')(x)
    sigm_out = Activation('sigmoid')(x)  
    return Merge(mode='mul')([tanh_out, sigm_out])

def ED_TCN(n_nodes, pool_sizes, conv_lens, n_classes, n_feat, max_len, 
      loss='categorical_crossentropy', causal=False, 
      optimizer="rmsprop", activation='norm_relu',
      compile_model=True):
  """Colin's ED_TCN model for segemation.
  Args:
    n_nodes: number of filter.
    pool_sizes: up/down sample stride.
    conv_lens: filter length.
    n_classes: number of classes for this kind of label.
    n_feat: the dumention of the feature.
    max_len: the number of frames for each video.
  Returns:
    model: compiled model."""
  n_layers = len(n_nodes)

  inputs = Input(shape=(max_len,n_feat))
  model = inputs
  # ---- Encoder ----
  for i in range(n_layers):
    # Pad beginning of sequence to prevent usage of future data
    if causal: model = ZeroPadding1D((conv_lens[i]//2,0))(model)
    model = Convolution1D(n_nodes[i], conv_lens[i], border_mode='same')(model)
    if causal: model = Cropping1D((0,conv_lens[i]//2))(model)

    model = SpatialDropout1D(0.3)(model)
    
    if activation=='norm_relu': 
      model = Activation('relu')(model)            
      model = Lambda(channel_normalization, name="encoder_norm_{}".format(i))(model)
    elif activation=='wavenet': 
      model = WaveNet_activation(model) 
    else:
      model = Activation(activation)(model)            
    
    model = MaxPooling1D(pool_sizes[i])(model)

  # ---- Decoder ----
  for i in range(n_layers):
    model = UpSampling1D(pool_sizes[-i-1])(model)
    if causal: model = ZeroPadding1D((conv_lens[-i-1]//2,0))(model)
    print n_nodes[-i-1], conv_lens[-i-1]
    model = Convolution1D(n_nodes[-i-1], conv_lens[-i-1], border_mode='same')(model)
    if causal: model = Cropping1D((0,conv_lens[-i-1]//2))(model)

    model = SpatialDropout1D(0.3)(model)

    if activation=='norm_relu': 
      model = Activation('relu')(model)
      model = Lambda(channel_normalization, name="decoder_norm_{}".format(i))(model)
    elif activation=='wavenet': 
      model = WaveNet_activation(model) 
    else:
      model = Activation(activation)(model)

  # Output FC layer
  model = TimeDistributed(Dense(n_classes, activation="softmax" ))(model)
  
  model = Model(input=inputs, output=model)

  if compile_model:
    model.compile(loss=loss, optimizer=optimizer, sample_weight_mode="temporal", metrics=['accuracy'])

  return model

  # Output FC layer
  model = TimeDistributed(Dense(n_classes, activation="softmax" ))(model)

  model = Model(input=inputs, output=model)
  model.compile(loss=loss, optimizer=optimizer, sample_weight_mode="temporal", metrics=['categorical_accuracy'])

#####################################################################
def train_model(model, max_len, get_cross_validation=False, non_zero=False):
  """For the 0/1 segemation task, load data, compile, fit, evaluate model, and predict frame labels.
  Args:
    model: model name.
    max_len: the number of frames for each video.
    get_cross_validation: whether to cross validate. 
    non_zero: whether to use the non-zero data. If true 
  Returns:
    loss_mean: loss for this model.
    acc_mean: accuracy for classification model.
    classes: predications. Predication for all the videos is using cross validation.
    y_test: test ground truth. Equal to all labels if using cross validation."""
  x = get_data.get_feature_tensor(feature_dir,feature_name,max_len)
  y = get_data.get_frame_01_labels(feature_dir,feature_name,max_len)
  y_video = get_data.get_labels(label_dir, label_name)
  y = np.array(y)
  print 'x', x.shape, 'y', y.shape
  np.set_printoptions(threshold='nan')

  if model == ED_TCN:
    n_nodes = [512, 512]  #, 1024]
    pool_sizes = [2, 2]  #, 2]
    conv_lens = [10, 10]  #, 10]
    causal = False
    model = ED_TCN(n_nodes, pool_sizes, conv_lens, 2, 512, max_len, 
      causal=causal, activation='norm_relu', optimizer='rmsprop')
    model.summary()

  loss = np.zeros((4))
  acc = np.zeros((4))
  classes = np.zeros((200,max_len, 2))
  if get_cross_validation == False:
    if non_zero == True:
      x,labels_new, y = get_data.non_zero_data(x,y_video,max_len, y, use_y_frame=True)
    y_cat = np_utils.to_categorical(y,num_classes=2)
    y_cat = np.reshape(y_cat, (-1, max_len, 2))
    x_train, x_test, y_train, y_test = cross_validation.train_test_split(x,y_cat,test_size=0.2, random_state=1)
    model.fit(x_train,y_train, validation_data=[x_test,y_test],epochs=5)
    loss_and_metrics = model.evaluate(x_test,y_test)
    loss_mean = loss_and_metrics[0]
    acc_mean  = loss_and_metrics[1]
    classes = model.predict(x_test)
  elif get_cross_validation == True:
    y_cat = np_utils.to_categorical(y,num_classes=2)
    y_cat = np.reshape(y_cat, (200, max_len, 2))
    x_train_cro, y_train_cro, x_test_cro, y_test_cro = train.set_cross_validation(x, y_cat)
    for i in range(4):
      print i
      model.fit(x_train_cro[i], y_train_cro[i],batch_size=20)
      loss_and_metrics = model.evaluate(x_test_cro[i], y_test_cro[i]) 
      loss[i] = loss_and_metrics[0]
      acc[i]  = loss_and_metrics[1]
      classes[i*50:(i+1)*50] = model.predict(x_test_cro[i])
    loss_mean = np.mean(loss)
    acc_mean = np.mean(acc)
    y_test = y_cat
  print 'loss_mean: ', loss_mean, ' ', 'acc_mean: ', acc_mean
  return loss_mean, acc_mean, classes, y_test


if __name__ == '__main__':
  loss_mean, acc_mean, classes, y_cat = train_model(ED_TCN, 48, get_cross_validation=False, non_zero=True)
  y_cat = np.reshape(y_cat, (y_cat.shape[0]*y_cat.shape[1], y_cat.shape[2]))
  classes = np.reshape(classes, (classes.shape[0]*classes.shape[1], classes.shape[2]))
  y_test = train.to_vector(y_cat)
  classes = train.to_vector(classes)
  print 'ground truth: ', y_test[:100]
  print 'predict: ', classes[:100]

  cnf_matrix = sklearn.metrics.confusion_matrix(y_test, classes)

  plt.figure()
  train.plot_confusion_matrix(cnf_matrix,classes=[0,1], normalize=False,
                        title='Confusion matrix, without normalization')
  plt.show()
