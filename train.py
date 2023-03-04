import tensorflow as tf
import cv2
import numpy as np
import matplotlib.pyplot as plt
import os
from models import get_generator, get_discriminator, get_feature_extractor
import argparse
from glob import glob

parser = argparse.ArgumentParser()
parser.add_argument('--epochs', required=False, default=100, help='epochs')
parser.add_argument('--batchs', required=False, default=100, help='batchs')
parser.add_argument('--lr_g', required=False, default=0.00001, help='learning rate of generator')
parser.add_argument('--lr_d', required=False, default=0.00001, help='learning rate of discriminator')
parser.add_argument('--train_dir', required=False, default="./train/", help='directory of image to train / 학습 할 이미지 위치')
parser.add_argument('--load_model', required=False, default=True, help='load saved model / 저장된 모델 불러오기 (1: True, 0: False)')
parser.add_argument('--use_cpu', required=False, default=False, help='forced to use CPU only / CPU 만 이용해 학습하기 (1: True, 0: False)')
args = parser.parse_args()

epochs = args.epochs
batchs = args.batchs
lr_g = args.lr_g
lr_d = args.lr_d
train_dir =  args.train_dir
load_model =  args.load_model
use_cpu =  args.use_cpu

if use_cpu: os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

# 모델 불러오기 or 새로 생성하기
if load_model:

    if os.path.isfile('Generator.h5'):
        Generator= tf.keras.models.load_model('Generator.h5')
        print('Generator loaded')
    else:
        print('Cant load Generator')
        Generator = get_generator(include_bn=True, separable_cnn=False)

    if os.path.isfile('Discriminator.h5'):
        Discriminator = tf.keras.models.load_model('Discriminator.h5')
        print('Discriminator loaded')
    else:
        print('Cant load Discriminator')
        Discriminator = get_discriminator(include_bn=True)

else:
    Generator = get_generator(include_bn=True, separable_cnn=False)
    Discriminator = get_discriminator(include_bn=True)

# feature map 생성을 위한 feature extractor 선언
feature_extractor = get_feature_extractor(out_layer=20)
feature_extractor.trainable = False

def RGB2BGR(image):
    channels = tf.unstack(image, axis=-1)
    image    = tf.stack([channels[2], channels[1], channels[0]], axis=-1)
    return image

imgs = []
mse = tf.losses.mean_squared_error
bce = tf.losses.binary_crossentropy
optim_g = tf.optimizers.Adam(lr_g, beta_1=0.9)
optim_d = tf.optimizers.Adam(lr_d, beta_1=0.9)
update_alternate = 0
iter_count = 1
im_inx = glob(train_dir + "*.png")
im_inx += glob(train_dir + "*.jpg")
im_inx += glob(train_dir + "*.jpeg")
im_inx += glob(train_dir + "*/*.png")
im_inx += glob(train_dir + "*/*.jpg")
im_inx += glob(train_dir + "*/*.jpeg")

for epoch in range(1, epochs+1):
    np.random.shuffle(im_inx)
    ssmi_scores = []
    for i in range(1, len(im_inx)+1):
        try:
            img = cv2.imread(im_inx[i-1])
            img = tf.image.random_crop(img, (96,96,3)).numpy()
            imgs.append(img)
        except: 
            continue

        if len(imgs) >= batchs or epoch == epochs:
            imgs_tensor_hr = np.array(imgs, dtype=np.float32)
            imgs_tensor_lr = tf.image.resize(imgs_tensor_hr, (24, 24), method=tf.image.ResizeMethod.BICUBIC).numpy()
            imgs_tensor_hr = imgs_tensor_hr / 127.5 -1
            imgs_tensor_lr = imgs_tensor_lr / 255
            imgs = []

            with tf.GradientTape() as tape:
                imgs_tensor_sr = Generator(imgs_tensor_lr)
                hr_disc = Discriminator(imgs_tensor_hr)
                sr_disc = Discriminator(imgs_tensor_sr)
                imgs_tensor_sr_feature_map = feature_extractor(imgs_tensor_sr) / 12.75
                imgs_tensor_hr_feature_map = feature_extractor(imgs_tensor_hr) / 12.75
                loss_g = loss_d = 0
                if update_alternate == 0:
                    loss_g = -tf.math.log(sr_disc) * 1e-3
                    loss_g = tf.reshape(loss_g, shape=(-1))
                    w, d = imgs_tensor_sr_feature_map.shape[1:3]
                    loss_g += tf.reduce_sum(tf.square(imgs_tensor_sr_feature_map - imgs_tensor_hr_feature_map), axis=(1,2,3)) / (w*d)
                else:
                    loss_d = bce(tf.zeros(shape = sr_disc.shape), sr_disc) + bce(tf.ones(shape = hr_disc.shape), hr_disc)
            imgs_tensor_sr = imgs_tensor_sr.numpy()
            imgs_tensor_sr = (imgs_tensor_sr + 1) / 2
            imgs_tensor_sr[imgs_tensor_sr > 1] = 1
            imgs_tensor_sr[imgs_tensor_sr < 0] = 0
            imgs_tensor_hr = (imgs_tensor_hr + 1) / 2

            print("\repochs:", epoch, ", step:", i, len(im_inx), ", G loss:", round(np.mean(loss_g),5), ", D loss:", round(np.mean(loss_d), 5), "ssim:", round(np.mean(tf.image.ssim(imgs_tensor_sr, imgs_tensor_hr, max_val = 1).numpy()), 5), end="")
            ssmi_scores.append(np.mean(tf.image.ssim(imgs_tensor_sr, imgs_tensor_hr, max_val = 1).numpy()))

            if update_alternate == 0:
                optim_g.minimize(loss_g, Generator.trainable_variables, tape=tape)
                update_alternate = 1

            else:
                optim_d.minimize(loss_d, Discriminator.trainable_variables, tape = tape)
                update_alternate = 0
            iter_count += 1
            
            if iter_count % 1000 == 0:
                Generator.save('Generator.h5')
                Discriminator.save('Discriminator.h5')

    print("\nepochs:", epoch, 'ssmi mean:', round(np.mean(ssmi_scores), 5))
    Generator.save('Generator.h5')
    Discriminator.save('Discriminator.h5')