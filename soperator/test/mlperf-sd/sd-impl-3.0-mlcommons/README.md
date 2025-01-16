# Problem

Text to image: Stable Diffusion (SD)

# Benchmark

## Dataset

The benchmark employs two datasets:

1. Training: a subset of [laion-400m](https://laion.ai/blog/laion-400-open-dataset)
2. Validation: a subset of [coco-2014 validation](https://cocodataset.org/#download)

### Laion 400m

The benchmark uses a CC-BY licensed subset of the Laion400 dataset.

The LAION datasets comprise lists of URLs for original images, paired with the ALT text linked to those images.

### COCO-2014

The COCO-2014-validation dataset consists of 40,504 images and 202,654 annotations.

## Checkpoints

The benchmark utilizes several network architectures for both the training and validation processes:

1. **Stable Diffusion**: This component leverages StabilityAI's `512-base-ema.ckpt` checkpoint from HuggingFace. While the checkpoint includes weights for the UNet, VAE, and OpenCLIP text embedder, the UNet weights are not used and are discarded when loading the weights.
2. **Inception**: The Inception network is employed during validation to compute the Fréchet Inception Distance (FID) score.
3. **OpenCLIP ViT-H-14 Model**: This model is utilized for the computation of the CLIP score.

## The Model

Stable Diffusion v2 is a latent diffusion model which combines an autoencoder with a diffusion model that is trained in the latent space of the autoencoder.

During training:
- Images are encoded through an encoder, which turns images into latent representations. The autoencoder uses a relative downsampling factor of 8 and maps images of shape 512 x 512 x 3 to latents of shape 64 x 64 x 4
- Text prompts are encoded through the OpenCLIP-ViT/H text-encoder, the output embedding vector has a lengh of 1024.
- The output of the text encoder is fed into the UNet backbone of the latent diffusion model via cross-attention.
- The loss is a reconstruction objective between the noise that was added to the latent and the prediction made by the UNet. We also use the so-called v-objective, see https://arxiv.org/abs/2202.00512.

The UNet backbone in our model serves as the sole trainable component, initialized from random weights.
Conversely, the weights of both the image and text encoders are loaded from a pre-existing checkpoint and kept static throughout the training procedure.

Although our benchmark aims to adhere to the original Stable Diffusion v2 implementation as closely as possible,
it's important to note some key deviations:
1. The group norm of the UNet within our code uses a group size of 16 instead of the 32 used in the original implementation. This adjustment can be found in our code at this [link](./ldm/modules/diffusionmodules/util.py#L209)

## Validation metrics

### FID

FID is a measure of similarity between two datasets of images.
It was shown to correlate well with human judgement of visual quality and is most often used to evaluate the quality of samples of Generative Adversarial Networks.
FID is calculated by computing the [Fréchet distance](https://en.wikipedia.org/wiki/Fr%C3%A9chet_distance) between two Gaussians fitted to feature representations of the Inception network.
A lower FID implies a better image quality.

Further insights and an independent evaluation of the FID score can be found in [Are GANs Created Equal? A Large-Scale Study.](https://arxiv.org/abs/1711.10337)

### CLIP

CLIP is a reference free metric that can be used to evaluate the correlation between a caption for an image and the actual content of the image, it has been found to be highly correlated with human judgement.
A higher CLIP Score implies that the caption matches closer to image.

## Quality

### Metric

Both FID and CLIP are used to evaluate the model's quality.

### Target

`FID <= 90` and `CLIP >= 0.15`.

## Evaluation

### Frequency

Every 512,000 images, or `CEIL(512000 / global_batch_size)` if 512,000 is not divisible by GBS.

### Thoroughness

All the prompts in the [coco-2014](#coco-2014) validation subset.

# Training

We provide Slurm scripts to submit multi-node training batch jobs.

The example command to submit a batch job is:
```bash
scripts/slurm/sbatch.sh \
  --num-nodes 2 \
  --gpus-per-node 8 \
  --config configs./configs/train_02x08x08.yaml \
  --checkpoint /data/mlcommons/sd-checkpoint-3.0/512-base-ema.ckpt
```
