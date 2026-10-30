// Adaptation: expose upstream texture shader; bypass experimental HTML capture.
"use client";


import React from "react";


const QUAD = new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]);

const VERTEX_SHADER = `#version 300 es
in vec2 a_pos;
out vec2 v_uv;
void main() {
  v_uv = vec2(a_pos.x * 0.5 + 0.5, 0.5 - a_pos.y * 0.5);
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;

const LAYER: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  width: "100%",
  height: "100%",
};

const OUTPUT_LAYER: React.CSSProperties = { ...LAYER, pointerEvents: "none" };





export type SceneShaderFrame<Props> = {
  gl: WebGL2RenderingContext;
  uniform: (name: string) => WebGLUniformLocation | null;
  width: number;
  height: number;
  progress: number;
  passedProps: Props;
};

export type SceneShaderDrawParams<Props> = {
  from: OffscreenCanvas | null;
  to: OffscreenCanvas | null;
  width: number;
  height: number;
  progress: number;
  passedProps: Props;
};

export type SceneShaderInstance<Props> = {
  draw: (params: SceneShaderDrawParams<Props>) => void;
  clear: () => void;
  cleanup: () => void;
};

export type SceneShader<Props> = (
  canvas: OffscreenCanvas,
) => SceneShaderInstance<Props>;

export type SceneFilterFrame<Props> = {
  gl: WebGL2RenderingContext;
  uniform: (name: string) => WebGLUniformLocation | null;
  width: number;
  height: number;
  frame: number;
  time: number;
  passedProps: Props;
};

export type SceneFilterDrawParams<Props> = {
  scene: OffscreenCanvas | null;
  width: number;
  height: number;
  frame: number;
  time: number;
  passedProps: Props;
};

export type SceneFilterInstance<Props> = {
  draw: (params: SceneFilterDrawParams<Props>) => void;
  clear: () => void;
  cleanup: () => void;
};

export type SceneFilter<Props> = (
  canvas: OffscreenCanvas,
) => SceneFilterInstance<Props>;

function compileShader(
  gl: WebGL2RenderingContext,
  source: string,
  type: GLenum,
): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) {
    throw new Error("canvas-presentation: failed to create shader");
  }
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`canvas-presentation: failed to compile shader: ${log}`);
  }
  return shader;
}

function createProgram(
  gl: WebGL2RenderingContext,
  fragment: string,
): WebGLProgram {
  const program = gl.createProgram();
  if (!program) {
    throw new Error("canvas-presentation: failed to create program");
  }
  const vs = compileShader(gl, VERTEX_SHADER, gl.VERTEX_SHADER);
  const fs = compileShader(gl, fragment, gl.FRAGMENT_SHADER);
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program);
    gl.deleteProgram(program);
    throw new Error(`canvas-presentation: failed to link program: ${log}`);
  }
  return program;
}

function createSceneTexture(gl: WebGL2RenderingContext): WebGLTexture {
  const texture = gl.createTexture();
  if (!texture) {
    throw new Error("canvas-presentation: failed to create texture");
  }
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texImage2D(
    gl.TEXTURE_2D,
    0,
    gl.RGBA,
    1,
    1,
    0,
    gl.RGBA,
    gl.UNSIGNED_BYTE,
    new Uint8Array([0, 0, 0, 0]),
  );
  return texture;
}

function createQuadSurface(canvas: OffscreenCanvas, fragment: string) {
  const gl = canvas.getContext("webgl2", { premultipliedAlpha: true });
  if (!gl) {
    throw new Error("canvas-presentation: WebGL2 is unavailable");
  }

  const program = createProgram(gl, fragment);
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, QUAD, gl.STATIC_DRAW);
  const aPos = gl.getAttribLocation(program, "a_pos");
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

  const locations = new Map<string, WebGLUniformLocation | null>();
  const uniform = (name: string) => {
    const cached = locations.get(name);
    if (cached !== undefined) {
      return cached;
    }
    const location = gl.getUniformLocation(program, name);
    locations.set(name, location);
    return location;
  };

  const clear = () => {
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
  };

  const textures: WebGLTexture[] = [];
  const createTexture = () => {
    const texture = createSceneTexture(gl);
    textures.push(texture);
    return texture;
  };

  const begin = (width: number, height: number) => {
    gl.viewport(0, 0, width, height);
    clear();
    gl.useProgram(program);
    gl.bindVertexArray(vao);
  };

  const bindScene = (
    image: OffscreenCanvas | null,
    texture: WebGLTexture,
    unit: number,
    name: string,
  ) => {
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    if (image) {
      gl.texImage2D(
        gl.TEXTURE_2D,
        0,
        gl.RGBA,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        image,
      );
    }
    gl.uniform1i(uniform(name), unit);
  };

  const draw = () => gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

  const cleanup = () => {
    gl.deleteProgram(program);
    for (const texture of textures) {
      gl.deleteTexture(texture);
    }
    gl.deleteBuffer(buffer);
    gl.deleteVertexArray(vao);
  };

  return {
    gl,
    uniform,
    clear,
    createTexture,
    begin,
    bindScene,
    draw,
    cleanup,
  };
}

export function makeSceneShader<Props extends Record<string, unknown>>(
  fragment: string,
  setUniforms?: (frame: SceneShaderFrame<Props>) => void,
): SceneShader<Props> {
  return (canvas) => {
    const surface = createQuadSurface(canvas, fragment);
    const fromTexture = surface.createTexture();
    const toTexture = surface.createTexture();

    return {
      clear: surface.clear,
      cleanup: surface.cleanup,
      draw: ({ from, to, width, height, progress, passedProps }) => {
        surface.begin(width, height);
        surface.bindScene(from, fromTexture, 0, "u_from");
        surface.bindScene(to, toTexture, 1, "u_to");

        surface.gl.uniform1f(surface.uniform("u_progress"), progress);
        surface.gl.uniform1f(surface.uniform("u_aspect"), width / height);
        setUniforms?.({
          gl: surface.gl,
          uniform: surface.uniform,
          width,
          height,
          progress,
          passedProps,
        });

        surface.draw();
      },
    };
  };
}


