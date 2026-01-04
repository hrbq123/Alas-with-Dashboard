# docker build -t hgjazhgj/alas:latest .
# docker run -v ${PWD}:/app/AzurLaneAutoScript -p 22267:22267 --name alas -it --rm hgjazhgj/alas

FROM python:3.7-buster

WORKDIR /app/AzurLaneAutoScript

COPY deploy/docker/requirements.txt /tmp/requirements.txt

# Initial download of UiAutomator2 is slow outside of China using appetizer mirror, switch to GitHub
RUN apt update \
    && apt install -y git adb libgomp1 openssh-client pkg-config libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev libswscale-dev libswresample-dev libavfilter-dev libopenblas-dev libsm6 libxext6 libgl1 \
    && git config --global --add safe.directory '*' \
    && pip install --upgrade pip \
    && pip install "cython<3" \
    && pip install --no-build-isolation av==10.0.0 \
    && pip install -r /tmp/requirements.txt \
    && python -c "import mxnet; import cnocr; print('OCR dependencies loaded successfully')" \
    && rm /tmp/requirements.txt \
    && rm -r ~/.cache/pip

COPY . /app/AzurLaneAutoScript

CMD python gui.py
