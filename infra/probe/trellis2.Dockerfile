# syntax=docker/dockerfile:1.7
# A THROWAWAY PROBE, not a deployable image. It answers one question before the
# real build spends three hours on it: do TRELLIS.2's four source-only CUDA
# extensions compile for an L4, in Cloud Build, with no GPU present?
#
#   gcloud builds submit --config infra/probe/trellis2-probe.yaml .
#
# Nothing is pushed. Success is the final RUN printing every import.

FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

# Ada Lovelace. The builder has no GPU, so the target architecture has to be
# stated or nvcc emits nothing and the extensions fail at import instead.
ENV DEBIAN_FRONTEND=noninteractive \
    TORCH_CUDA_ARCH_LIST="8.9" \
    FORCE_CUDA=1 \
    MAX_JOBS=8 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3.11 python3.11-dev python3-pip git ninja-build build-essential \
      libgl1 libglib2.0-0 ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && ln -sf /usr/bin/python3.11 /usr/bin/python

# torch first and alone: every extension below compiles against its headers.
RUN pip install --upgrade pip \
 && pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124

# xformers instead of flash-attn. Upstream offers it as the alternative backend,
# it ships a wheel, and flash-attn is the single worst compile in the set.
RUN pip install xformers==0.0.35 ninja packaging wheel setuptools

ARG TRELLIS2_REPO=https://github.com/microsoft/TRELLIS.2.git
WORKDIR /probe
RUN git clone -q --recursive "${TRELLIS2_REPO}" trellis2

# One RUN per extension so a failure names which one, rather than collapsing
# four possible causes into a single red layer.
WORKDIR /probe/trellis2
RUN pip install -v ./extensions/o_voxel 2>&1 | tail -25
RUN pip install -v ./extensions/flexgemm 2>&1 | tail -25
RUN pip install -v ./extensions/nvdiffrec 2>&1 | tail -25
RUN pip install -v git+https://github.com/NVlabs/nvdiffrast.git 2>&1 | tail -25

# Import is the real test: a wheel that builds but cannot load is worth nothing.
RUN python -c "\
import torch, xformers; \
print('torch', torch.__version__, 'cuda', torch.version.cuda); \
import o_voxel; print('o_voxel OK'); \
import flexgemm; print('flexgemm OK'); \
import nvdiffrast.torch; print('nvdiffrast OK'); \
print('ALL EXTENSIONS IMPORT')"
