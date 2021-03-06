import numpy as np
import warnings
import threading
import os
from keras.callbacks import ReduceLROnPlateau
import sklearn
from sklearn import cross_validation
import matplotlib.pyplot as plt
from functools import partial
import itertools

import keras
from keras.models import Sequential, Model
from keras.layers import Input, Dense, TimeDistributed, merge, Lambda
from keras.layers.core import *
from keras.layers.convolutional import *
from keras.layers.recurrent import *
from keras.regularizers import l2,l1
from keras.layers.normalization import BatchNormalization
import tensorflow as tf
from keras import backend as K
from keras.utils import np_utils
from keras import optimizers
from keras.activations import relu
from keras.utils import np_utils
from keras.optimizers import RMSprop,SGD,Adam
from keras.callbacks import ModelCheckpoint

import get_data
warnings.filterwarnings("ignore")

# Path to the directories of features and labels
feature_dir = '/home/ye/Works/pain'
label_dir = '/home/ye/Works/pain/Sequence_Labels'
feature_name = 'feature_from_verification_model.mat'
label_name = 'OPR'

#######################################################################
# TCN models
def TK_TCN_resnet(
           n_classes, 
           feat_dim,
           max_len,
           gap=1,
           dropout=0.0,
           activation="relu"):
  """Reviced TK'S TCN model. num_block = 2. initial_conv_num=64.
  Args:
    n_classes: number of classes for this kind of label.
    feat_dim: the dumention of the feature.
    max_len: the number of frames for each video.
  Returns:
    model: uncompiled model."""
  ROW_AXIS = 1
  CHANNEL_AXIS = 2
  
  initial_conv_len = 8
  initial_conv_num = 64

  config = [ 
             [(1,8,64)],
             [(1,8,64)],
             [(1,8,64)],
             [(2,8,128)],
             [(1,8,128)],
             [(1,8,128)],
           ]

  input = Input(shape=(max_len,feat_dim))
  model = input

  model = Convolution1D(initial_conv_num, 
                              initial_conv_len,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=1)(model)

  for depth in range(0,len(config)):
    blocks = []
    for stride,filter_dim,num in config[depth]:
      ## residual block
      bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
      relu = Activation(activation)(bn)
      dr = Dropout(dropout)(relu)
      conv = Convolution1D(num, 
                              filter_dim,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=stride)(dr)
      #dr = Dropout(dropout)(conv)


      ## potential downsample
      conv_shape = K.int_shape(conv)
      model_shape = K.int_shape(model)
      if conv_shape[CHANNEL_AXIS] != model_shape[CHANNEL_AXIS]:
        model = Convolution1D(num, 
                              1,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=2)(model)

      ## merge block
      model = merge([model,conv],mode='sum',concat_axis=CHANNEL_AXIS)

  ## final bn+relu
  bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
  model = Activation(activation)(bn)


  if gap:
    pool_window_shape = K.int_shape(model)
    gap = AveragePooling1D(pool_window_shape[ROW_AXIS],
                           stride=1)(model)
    flatten = Flatten()(gap)
  else:
    flatten = Flatten()(model)

  dense = Dense(output_dim=n_classes,
        init="he_normal",
        activation="softmax")(flatten)

  model = Model(input=input, output=dense)
  # optimizer = SGD(lr=0.01, momentum=0.9, decay=0.0, nesterov=True) 
  # model.compile(loss='categorical_crossentropy', optimizer=optimizer,metrics=['accuracy'])
  return model

def TK_TCN_regression(
           n_classes, 
           feat_dim,
           max_len,
           gap=1,
           dropout=0.0,
           W_regularizer=l1(1.e-4),
           activation="relu"):
  """TCN regression model. num_block = 2. initial_conv_num=64. The last layer is fullly-connected instead of softmax.
  Args:
    n_classes: number of classes for this kind of label.
    feat_dim: the dumention of the feature.
    max_len: the number of frames for each video.
  Returns:
    model: uncompiled model."""

  ROW_AXIS = 1
  CHANNEL_AXIS = 2
  
  initial_conv_len = 8
  initial_conv_num = 64

  config = [ 
             [(1,8,64)],
             [(1,8,64)],
             [(1,8,64)],
             [(2,8,128)],
             [(1,8,128)],
             [(1,8,128)],
           ]

  input = Input(shape=(max_len,feat_dim))
  model = input

  model = Convolution1D(initial_conv_num, 
                              initial_conv_len,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=1,
                              W_regularizer=W_regularizer)(model)

  for depth in range(0,len(config)):
    blocks = []
    for stride,filter_dim,num in config[depth]:
      ## residual block
      bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
      relu = Activation(activation)(bn)
      dr = Dropout(dropout)(relu)
      conv = Convolution1D(num, 
                              filter_dim,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=stride,
                              W_regularizer=W_regularizer)(dr)

      ## potential downsample
      conv_shape = K.int_shape(conv)
      model_shape = K.int_shape(model)
      if conv_shape[CHANNEL_AXIS] != model_shape[CHANNEL_AXIS]:
        model = Convolution1D(num, 
                              1,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=2,
                              W_regularizer=W_regularizer)(model)

      ## merge block
      model = merge([model,conv],mode='sum',concat_axis=CHANNEL_AXIS)

  ## final bn+relu
  bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
  model = Activation(activation)(bn)

  if gap:
    pool_window_shape = K.int_shape(model)
    gap = AveragePooling1D(pool_window_shape[ROW_AXIS],
                           stride=1)(model)
    flatten = Flatten()(gap)
  else:
    flatten = Flatten()(model)

  dense = Dense(output_dim=n_classes,
	    init="he_normal",
	    activation="softmax")(flatten)
  dense = Dense(output_dim=1,
        init="normal")(dense)

  model = Model(input=input, output=dense)
  # optimizer = SGD(lr=0.01, momentum=0.9, decay=0.0, nesterov=True) 
  # model.compile(loss='mean_absolute_error', optimizer = 'adam')
  return model

def TCN_V1(
           n_classes, 
           feat_dim,
           max_len,
           gap=1,
           dropout=0.0,
           activation="relu"):
  """TCN model. num_block = 3. initial_conv_num=64.
  Args:
    n_classes: number of classes for this kind of label.
    feat_dim: the dumention of the feature.
    max_len: the number of frames for each video.
  Returns:
    model: uncompiled model."""

  ROW_AXIS = 1
  CHANNEL_AXIS = 2
  
  initial_conv_len = 8
  initial_conv_num = 64

  config = [ 
             [(1,8,64)],
             [(1,8,64)],
             [(1,8,64)],
             [(2,8,128)],
             [(1,8,128)],
             [(1,8,128)],
             [(2,8,256)],
             [(1,8,256)],
             [(1,8,256)],
           ]

  input = Input(shape=(max_len,feat_dim))
  model = input

  model = Convolution1D(initial_conv_num, 
                              initial_conv_len,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=1)(model)

  for depth in range(0,len(config)):
    blocks = []
    for stride,filter_dim,num in config[depth]:
      ## residual block
      bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
      relu = Activation(activation)(bn)
      dr = Dropout(dropout)(relu)
      conv = Convolution1D(num, 
                              filter_dim,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=stride)(dr)

      ## potential downsample
      conv_shape = K.int_shape(conv)
      model_shape = K.int_shape(model)
      if conv_shape[CHANNEL_AXIS] != model_shape[CHANNEL_AXIS]:
        model = Convolution1D(num, 
                              1,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=2)(model)

      ## merge block
      model = merge([model,conv],mode='sum',concat_axis=CHANNEL_AXIS)

  ## final bn+relu
  bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
  model = Activation(activation)(bn)


  if gap:
    pool_window_shape = K.int_shape(model)
    gap = AveragePooling1D(pool_window_shape[ROW_AXIS],
                           stride=1)(model)
    flatten = Flatten()(gap)
  else:
    flatten = Flatten()(model)

  dense = Dense(output_dim=n_classes,
        init="he_normal",
        activation="softmax")(flatten)

  model = Model(input=input, output=dense)
  # optimizer = SGD(lr=0.01, momentum=0.9, decay=0.0, nesterov=True) 
  # model.compile(loss='categorical_crossentropy', optimizer=optimizer,metrics=['accuracy'])
  return model

def TCN_V2(
           n_classes, 
           feat_dim,
           max_len,
           gap=1,
           dropout=0.0,
           activation="relu"):
  """TCN model. num_block = 2. initial_conv_num=64. block_size = 5.
  Args:
    n_classes: number of classes for this kind of label.
    feat_dim: the dumention of the feature.
    max_len: the number of frames for each video.
  Returns:
    model: uncompiled model."""

  ROW_AXIS = 1
  CHANNEL_AXIS = 2
  
  initial_conv_len = 8
  initial_conv_num = 64

  config = [ 
             [(1,8,64)],
             [(1,8,64)],
             [(1,8,64)],
             [(1,8,64)],
             [(1,8,64)],
             [(2,8,128)],
             [(1,8,128)],
             [(1,8,128)],
             [(1,8,128)],
             [(1,8,128)],
           ]

  input = Input(shape=(max_len,feat_dim))
  model = input

  model = Convolution1D(initial_conv_num, 
                              initial_conv_len,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=1)(model)

  for depth in range(0,len(config)):
    blocks = []
    for stride,filter_dim,num in config[depth]:
      ## residual block
      bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
      relu = Activation(activation)(bn)
      dr = Dropout(dropout)(relu)
      conv = Convolution1D(num, 
                              filter_dim,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=stride)(dr)
      #dr = Dropout(dropout)(conv)


      ## potential downsample
      conv_shape = K.int_shape(conv)
      model_shape = K.int_shape(model)
      if conv_shape[CHANNEL_AXIS] != model_shape[CHANNEL_AXIS]:
        model = Convolution1D(num, 
                              1,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=2)(model)

      ## merge block
      model = merge([model,conv],mode='sum',concat_axis=CHANNEL_AXIS)

  ## final bn+relu
  bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
  model = Activation(activation)(bn)


  if gap:
    pool_window_shape = K.int_shape(model)
    gap = AveragePooling1D(pool_window_shape[ROW_AXIS],
                           stride=1)(model)
    flatten = Flatten()(gap)
  else:
    flatten = Flatten()(model)

  dense = Dense(output_dim=n_classes,
        init="he_normal",
        activation="softmax")(flatten)

  model = Model(input=input, output=dense)
  # optimizer = SGD(lr=0.01, momentum=0.9, decay=0.0, nesterov=True) 
  # model.compile(loss='categorical_crossentropy', optimizer=optimizer,metrics=['accuracy'])
  return model

def TCN_V3(
           n_classes, 
           feat_dim,
           max_len,
           gap=1,
           dropout=0.0,
           activation="relu"):
  """TCN model. num_block = 3. initial_conv_num=128, block_size = 3.
  Args:
    n_classes: number of classes for this kind of label.
    feat_dim: the dumention of the feature.
    max_len: the number of frames for each video.
  Returns:
    model: uncompiled model."""

  ROW_AXIS = 1
  CHANNEL_AXIS = 2
  
  initial_conv_len = 8
  initial_conv_num = 128

  config = [ 
             [(1,8,128)],
             [(1,8,128)],
             [(1,8,128)],
             [(2,8,256)],
             [(1,8,256)],
             [(1,8,256)],
           ]

  input = Input(shape=(max_len,feat_dim))
  model = input

  model = Convolution1D(initial_conv_num, 
                              initial_conv_len,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=1)(model)

  for depth in range(0,len(config)):
    blocks = []
    for stride,filter_dim,num in config[depth]:
      ## residual block
      bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
      relu = Activation(activation)(bn)
      dr = Dropout(dropout)(relu)
      conv = Convolution1D(num, 
                              filter_dim,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=stride)(dr)
      #dr = Dropout(dropout)(conv)


      ## potential downsample
      conv_shape = K.int_shape(conv)
      model_shape = K.int_shape(model)
      if conv_shape[CHANNEL_AXIS] != model_shape[CHANNEL_AXIS]:
        model = Convolution1D(num, 
                              1,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=2)(model)

      ## merge block
      model = merge([model,conv],mode='sum',concat_axis=CHANNEL_AXIS)

  ## final bn+relu
  bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
  model = Activation(activation)(bn)


  if gap:
    pool_window_shape = K.int_shape(model)
    gap = AveragePooling1D(pool_window_shape[ROW_AXIS],
                           stride=1)(model)
    flatten = Flatten()(gap)
  else:
    flatten = Flatten()(model)

  dense = Dense(output_dim=n_classes,
        init="he_normal",
        activation="softmax")(flatten)

  model = Model(input=input, output=dense)
  # optimizer = SGD(lr=0.01, momentum=0.9, decay=0.0, nesterov=True) 
  # model.compile(loss='categorical_crossentropy', optimizer=optimizer,metrics=['accuracy'])
  return model

def TCN_V4(
           n_classes, 
           feat_dim,
           max_len,
           gap=1,
           dropout=0.0,
           activation="relu"):
  """TCN model. num_block = 2. initial_conv_num=64, block_size = 3.
  Args:
    n_classes: number of classes for this kind of label.
    feat_dim: the dumention of the feature.
    max_len: the number of frames for each video.
  Returns:
    model: uncompiled model."""

  ROW_AXIS = 1
  CHANNEL_AXIS = 2
  
  initial_conv_len = 4
  initial_conv_num = 64

  config = [ 
             [(1,4,64)],
             [(1,4,64)],
             [(1,4,64)],
             [(2,4,128)],
             [(1,4,128)],
             [(1,4,128)],
           ]

  input = Input(shape=(max_len,feat_dim))
  model = input

  model = Convolution1D(initial_conv_num, 
                              initial_conv_len,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=1)(model)

  for depth in range(0,len(config)):
    blocks = []
    for stride,filter_dim,num in config[depth]:
      ## residual block
      bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
      relu = Activation(activation)(bn)
      dr = Dropout(dropout)(relu)
      conv = Convolution1D(num, 
                              filter_dim,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=stride)(dr)
      #dr = Dropout(dropout)(conv)


      ## potential downsample
      conv_shape = K.int_shape(conv)
      model_shape = K.int_shape(model)
      if conv_shape[CHANNEL_AXIS] != model_shape[CHANNEL_AXIS]:
        model = Convolution1D(num, 
                              1,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=2)(model)

      ## merge block
      model = merge([model,conv],mode='sum',concat_axis=CHANNEL_AXIS)

  ## final bn+relu
  bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
  model = Activation(activation)(bn)


  if gap:
    pool_window_shape = K.int_shape(model)
    gap = AveragePooling1D(pool_window_shape[ROW_AXIS],
                           stride=1)(model)
    flatten = Flatten()(gap)
  else:
    flatten = Flatten()(model)

  dense = Dense(output_dim=n_classes,
        init="he_normal",
        activation="softmax")(flatten)

  model = Model(input=input, output=dense)
  # optimizer = SGD(lr=0.01, momentum=0.9, decay=0.0, nesterov=True) 
  # model.compile(loss='categorical_crossentropy', optimizer=optimizer,metrics=['accuracy'])
  return model

def TCN_V5(
           n_classes, 
           feat_dim,
           max_len,
           gap=1,
           dropout=0.0,
           activation="relu"):
  """TCN model. num_block = 2. initial_conv_num=32, block_size = 3.
  Args:
    n_classes: number of classes for this kind of label.
    feat_dim: the dumention of the feature.
    max_len: the number of frames for each video.
  Returns:
    model: uncompiled model."""

  ROW_AXIS = 1
  CHANNEL_AXIS = 2
  
  initial_conv_len = 8
  initial_conv_num = 32

  config = [ 
             [(1,8,32)],
             [(1,8,32)],
             [(1,8,32)],
             [(2,8,64)],
             [(1,8,64)],
             [(1,8,64)],
           ]

  input = Input(shape=(max_len,feat_dim))
  model = input

  model = Convolution1D(initial_conv_num, 
                              initial_conv_len,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=1)(model)

  for depth in range(0,len(config)):
    blocks = []
    for stride,filter_dim,num in config[depth]:
      ## residual block
      bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
      relu = Activation(activation)(bn)
      dr = Dropout(dropout)(relu)
      conv = Convolution1D(num, 
                              filter_dim,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=stride)(dr)
      #dr = Dropout(dropout)(conv)


      ## potential downsample
      conv_shape = K.int_shape(conv)
      model_shape = K.int_shape(model)
      if conv_shape[CHANNEL_AXIS] != model_shape[CHANNEL_AXIS]:
        model = Convolution1D(num, 
                              1,
                              init="he_normal",
                              border_mode="same",
                              subsample_length=2)(model)

      ## merge block
      model = merge([model,conv],mode='sum',concat_axis=CHANNEL_AXIS)

  ## final bn+relu
  bn = BatchNormalization(mode=0, axis=CHANNEL_AXIS)(model)
  model = Activation(activation)(bn)


  if gap:
    pool_window_shape = K.int_shape(model)
    gap = AveragePooling1D(pool_window_shape[ROW_AXIS],
                           stride=1)(model)
    flatten = Flatten()(gap)
  else:
    flatten = Flatten()(model)

  dense = Dense(output_dim=n_classes,
        init="he_normal",
        activation="softmax")(flatten)

  model = Model(input=input, output=dense)
  # optimizer = SGD(lr=0.01, momentum=0.9, decay=0.0, nesterov=True) 
  # model.compile(loss='categorical_crossentropy', optimizer=optimizer,metrics=['accuracy'])
  return model

#######################################################################
def set_cross_validation(x,y):
	"""Get cross validation split with cv=4.
	Args:
		x: features.
		y: labels.
	Returns:
		x_train, y_train, x_test, y_test: cross splited x and y."""
	x_train_1 = x[50:]
	y_train_1 = y[50:]
	x_test_1 = x[:50]
	y_test_1 = y[:50]
	x_train_2 = np.concatenate((x[:50], x[100:]),axis=0)
	y_train_2 = np.concatenate((y[:50], y[100:]),axis=0)
	x_test_2 = x[50:100]
	y_test_2 = y[50:100]
	x_train_3 = np.concatenate((x[:100], x[150:]),axis=0)
	y_train_3 = np.concatenate((y[:100], y[150:]),axis=0)
	x_test_3 = x[100:150]
	y_test_3 = y[100:150]
	x_train_4 = x[:150]
	y_train_4 = y[:150]
	x_test_4 = x[150:]
	y_test_4 = y[150:]

	x_train = [x_train_1,x_train_2,x_train_3,x_train_4]
	y_train = [y_train_1,y_train_2,y_train_3,y_train_4]
	x_test = [x_test_1,x_test_2,x_test_3,x_test_4]
	y_test = [y_test_1,y_test_2,y_test_3,y_test_4]
	# print 'cross val shapes', x_train.shape, y_train.shape, x_test.shape, y_test.shape
	return x_train, y_train, x_test, y_test

def to_vector(mat):
	"""Convert categorical data into vector.
	Args:
		mat: onr-hot categorical data.
	Returns:
		out2: vectorized data."""
	out = np.zeros((mat.shape[0],mat.shape[1]))
	out2 = np.zeros((mat.shape[0]))
	for i in range(mat.shape[0]):
		for n, j in enumerate(mat[i]):
			if j == np.amax(mat[i]):
				out[i][n] = 1
				out2[i] = n

	return out2

def plot_confusion_matrix(cm, classes,
                          normalize=False,
                          title='Confusion matrix',
                          cmap=plt.cm.Blues):
    """
    This function prints and plots the confusion matrix.
    Normalization can be applied by setting `normalize=True`.
    From sklearn.com.
    """
    plt.imshow(cm, interpolation='nearest', cmap=cmap)
    plt.title(title)
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=45)
    plt.yticks(tick_marks, classes)

    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        print("Normalized confusion matrix")
    else:
        print('Confusion matrix, without normalization')

    print(cm)

    thresh = cm.max() / 2.
    for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
        plt.text(j, i, cm[i, j],
                 horizontalalignment="center",
                 color="white" if cm[i, j] > thresh else "black")

    plt.tight_layout()
    plt.ylabel('True label')
    plt.xlabel('Predicted label')	

def train_model(model, y_categorical, max_len, get_cross_validation=False, non_zero=False):
	"""Load data, compile, fit, evaluate model, and predict labels.
	Args:
		model: model name.
		y_categorical: whether to use the original label or one-hot label. True for classification models. False for regression models.
		max_len: the number of frames for each video.
		get_cross_validation: whether to cross validate. 
		non_zero: whether to use the non-zero data. If true 
	Returns:
		loss_mean: loss for this model.
		acc_mean: accuracy for classification model.
		classes: predications. Predication for all the videos is using cross validation.
		y_test: test ground truth. Equal to all labels if using cross validation."""

	# for label_numer = 'OPR', labels are [0,1,2,3,4,5]
	n_classes = 6
	x = get_data.get_feature_tensor(feature_dir,feature_name,max_len)
	y = get_data.get_labels(label_dir, label_name)
	if non_zero == True:
		x, y = get_data.non_zero_data(x,y,max_len, y)
	if y_categorical == True:
		y = np_utils.to_categorical(y)
	y = np.array(y)
	print 'x', x.shape, 'y', y.shape

	# choose model
	if model == TK_TCN_regression:
		model = TK_TCN_regression(n_classes=n_classes, feat_dim=512, max_len=max_len)
		model.compile(loss='mean_absolute_error', optimizer='sgd',metrics=['accuracy'])
	else:
		if model == TK_TCN_resnet:
			model = TK_TCN_resnet(n_classes=n_classes, feat_dim=512, max_len=max_len)
		elif model == TCN_V1:
			model = TCN_V1(n_classes=n_classes, feat_dim=512, max_len=max_len)
		elif model == TCN_V2:
			model = TCN_V2(n_classes=n_classes, feat_dim=512, max_len=max_len)
		elif model == TCN_V3:
			model = TCN_V3(n_classes=n_classes, feat_dim=512, max_len=max_len)
		elif model == TCN_V4:
			model = TCN_V4(n_classes=n_classes, feat_dim=512, max_len=max_len)
		elif model == TCN_V5:
			model = TCN_V5(n_classes=n_classes, feat_dim=512, max_len=max_len)
		# compile model
		optimizer = Adam(lr=0.01, beta_1=0.9, beta_2=0.999, epsilon=1e-08, decay=0.0)
		model.compile(loss='categorical_crossentropy', optimizer=optimizer,metrics=['categorical_accuracy'])
		# model.compile(loss='mean_absolute_error', optimizer=optimizer,metrics=['categorical_accuracy'])

	
	# visualize
	# model.summary()

	if get_cross_validation==True:
		loss = np.zeros((4))
		acc = np.zeros((4))
		classes = np.zeros((200, n_classes))
		x_train_cro, y_train_cro, x_test_cro, y_test_cro = set_cross_validation(x, y)
		for i in range(3):
			model.fit(x_train_cro[i], y_train_cro[i], validation_data=[x_test_cro[i],y_test_cro[i]], epochs=5)
			loss_and_metrics = model.evaluate(x_test_cro[i], y_test_cro[i])	
			loss[i] = loss_and_metrics[0]
			acc[i]  = loss_and_metrics[1]
			classes[i*50:(i+1)*50] = model.predict(x_test_cro[i])
		loss_mean = np.mean(loss)
		acc_mean = np.mean(acc)
		y_test = y
	elif get_cross_validation==False:
		x_train, x_test, y_train, y_test = cross_validation.train_test_split(x,y,test_size=0.2, random_state=1)
		model.fit(x_train, y_train, validation_data=[x_test,y_test], epochs=5)
		loss_mean, acc_mean = model.evaluate(x_test,y_test)
		classes = model.predict(x_test)
		
	return loss_mean, acc_mean, classes, y_test

if __name__ == '__main__':
	max_len = 100
	# get_cross_validation and non-zero could NOT be True in the same time.

	# print 'TK_TCN_resnet'
	# loss_mean, acc_mean, classes, y_test = train_model(TK_TCN_resnet, y_categorical=True, max_len=max_len,get_cross_validation=False,non_zero=True)
	print 'TCN_V1'
	loss_mean, acc_mean, classes, y_test = train_model(TCN_V1, y_categorical=True,max_len=max_len,get_cross_validation=True,non_zero=False)
	# print 'TCN_V2'
	# loss_mean, acc_mean, classes, y_test = train_model(TCN_V2, y_categorical=True,max_len=max_len,get_cross_validation=False,non_zero=True)
	# print 'TCN_V3'
	# loss_mean, acc_mean, classes, y_test = train_model(TCN_V3, y_categorical=True,max_len=max_len,get_cross_validation=False,non_zero=False)
	# print 'TCN_V4'
	# loss_mean, acc_mean, classes, y_test = train_model(TCN_V4, y_categorical=True,max_len=max_len,get_cross_validation=False,non_zero=True)
	# print 'TCN_V5'
	# loss_mean, acc_mean, classes, y_test = train_model(TCN_V5, y_categorical=True,max_len=max_len,get_cross_validation=False,non_zero=True)
	# print 'TK_TCN_regression'
	# loss_mean, acc_mean, classes, y_test = train_model(TK_TCN_regression, y_categorical=False, get_cross_validation=False, max_len=max_len,non_zero=False)
	print 'loss: ', loss_mean,' ', 'acc:', acc_mean
	classes = np.round(classes)
	# if one-hot lable, vectorization is required. For regression model it should't be done.
	y_test = to_vector(y_test)
	classes = to_vector(classes)
	print 'ground truth: ', y_test
	print 'predict: ', classes
	# create confusion matrix
	cnf_matrix = sklearn.metrics.confusion_matrix(y_test, classes)
	plt.figure()
	# if using non-zero data, classes=[1,2,3,4,5]
	plot_confusion_matrix(cnf_matrix,classes=[0,1,2,3,4,5], normalize=True,
	                      title='Confusion matrix, without normalization')
	plt.show()

	

