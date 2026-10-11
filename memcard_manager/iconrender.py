"""PS2 存档 3D 图标的软件渲染（numpy），用于界面里的动画预览。

模型、动画和贴图由 MyMC++ 的 ps2icon 解析，在 CPU 上用 numpy 光栅化。坐标、光照公式和
动画插值参考 MyMC++ 的 OpenGL 渲染器（gui/icon_renderer.py），速度、颜色和取景则对照
PS2 BIOS 浏览器的实机录像校准过：

* 顶点坐标 / 4096，Y、Z 取反；绕 Y 轴旋转；整体下移 2.5 居中
* 相机在 (0, 0, 5) 看向原点，55° 透视（MyMC++ 用 80°，图标显得很小）
* 光照：icon.sys 里的环境光 + 3 盏平行光（Lambert），逐顶点计算后插值
* 动画速度 = 每秒 60 帧 × 图标里的 anim_speed。对照 PS2 BIOS 浏览器实机录像确认：
  旺达与巨像（31 帧，1.0）0.517 秒一圈、寂静岭 4（119 帧，1.0，两个 BIOS 版本一样）1.98 秒、
  ICO（16 帧，0.5）0.534 秒，都与这个规则吻合。
  原版 mymc 固定每秒 60 帧（不看 anim_speed），MyMC++ 固定每秒 8 帧
* 背景：icon.sys 里四个角的颜色渐变，按 bg_alpha 半透明
* 顶点颜色 0x80 = 1.0（PS2 GS 的约定），所以除以 128 而不是 255
"""

import io
import math
import struct
from contextlib import redirect_stdout

import numpy as np
from mymcplusplus import ps2icon

ICON_SYS_SIZE = 964
_FOV = math.radians(55.0)    # 默认视角：比 MyMC++ 的 80° 窄，大小接近 PS2 浏览器；大图标会自动放宽
_BROWSER_BG = 0.3            # 半透明背景底下的颜色（PS2 浏览器的背景偏深灰）
_CAMERA_Z = 5.0
_ANIM_FPS = 60.0  # 每秒 60 帧，再乘以图标的 anim_speed（见模块说明）


class IconError(Exception):
    pass


def _icon_sys_params(icon_sys):
    """从 icon.sys 取背景色和光照。"""
    if not icon_sys or len(icon_sys) < ICON_SYS_SIZE or icon_sys[:4] != b"PS2D":
        return None
    f = struct.unpack_from("<4sHHII16I12f16f", icon_sys)
    bg_alpha = f[4]
    # 对照实机录像：背景色按 0-255 直接用（ICO 的 (13,73,147) 在浏览器里就是这个颜色），
    # 再按 bg_alpha（0x80 = 不透明）盖在浏览器自己的深灰背景上
    bg = np.array(f[5:21], dtype=np.float32).reshape(4, 4)[:, :3] / 255.0
    alpha = min(bg_alpha, 0x80) / 128.0
    bg = bg * alpha + _BROWSER_BG * (1.0 - alpha)
    light_dirs = np.array(f[21:33], dtype=np.float32).reshape(3, 4)[:, :3]
    light_colors = np.array(f[33:45], dtype=np.float32).reshape(3, 4)[:, :3]
    ambient = np.array(f[45:48], dtype=np.float32)
    n = np.linalg.norm(light_dirs, axis=1, keepdims=True)
    light_dirs = np.where(n > 0.01, light_dirs / np.maximum(n, 1e-6), 0.0)
    return {"bg": np.clip(bg, 0, 1), "bg_alpha": bg_alpha, "light_dirs": light_dirs,
            "light_colors": light_colors, "ambient": ambient}


class IconModel:
    """解析好的图标，可以按时间和角度渲染成 RGB 图像。"""

    def __init__(self, ico_data, icon_sys=None):
        if not ico_data:
            raise IconError("没有图标文件")
        try:
            with redirect_stdout(io.StringIO()):  # ps2icon 会 print 警告
                icon = ps2icon.Icon(ico_data)
        except Exception as e:  # noqa
            raise IconError("图标文件无法解析: %s" % e)
        n = icon.vertex_count - icon.vertex_count % 3
        s = icon.animation_shapes
        if n == 0 or s == 0 or icon.vertex_data is None:
            raise IconError("图标里没有模型")
        flip = np.array([1.0, -1.0, -1.0], dtype=np.float32)

        verts = np.frombuffer(bytes(icon.vertex_data), dtype="<i2")
        verts = verts.reshape(s, icon.vertex_count, 3)[:, :n].astype(np.float32)
        self.shapes = verts / 4096.0 * flip
        self.fov = self._fit_fov()
        nuv = np.frombuffer(bytes(icon.normal_uv_data), dtype="<i2")
        nuv = nuv.reshape(icon.vertex_count, 5)[:n].astype(np.float32)
        normals = nuv[:, :3] * flip
        nl = np.linalg.norm(normals, axis=1, keepdims=True)
        self.normals = normals / np.maximum(nl, 1e-6)
        self.uv = nuv[:, 3:5] / 4096.0
        col = np.frombuffer(bytes(icon.color_data), dtype=np.uint8).reshape(icon.vertex_count, 4)
        # PS2 的 GS 把 0x80 当作 1.0（MyMC++ 除以 255，图标会暗一半）
        self.colors = col[:n, :3].astype(np.float32) / 128.0

        tex = icon.texture
        if tex is None or len(tex) < ps2icon.TEXTURE_WIDTH * ps2icon.TEXTURE_HEIGHT * 2:
            self.texture = None  # 没有贴图：只用顶点颜色
        else:
            t = np.frombuffer(bytes(tex), dtype="<u2").reshape(ps2icon.TEXTURE_HEIGHT,
                                                                ps2icon.TEXTURE_WIDTH)
            rgb = np.stack([t & 31, (t >> 5) & 31, (t >> 10) & 31], axis=-1)
            self.texture = rgb.astype(np.float32) / 31.0

        self.duration = float(icon.frame_length)
        self.anim_speed = icon.anim_speed if 0.0 < icon.anim_speed <= 16.0 else 1.0
        self.frames = []
        for fr in icon.frames:
            keys = [(k.time, k.value) for k in fr.keys]
            if fr.shape_id == 0:
                keys.append((0.0, 1.0))
            if keys and fr.shape_id < s:
                self.frames.append((fr.shape_id, keys))

        p = _icon_sys_params(icon_sys) if icon_sys else None
        if p is None:
            p = {"bg": np.full((4, 3), 0.15, np.float32), "bg_alpha": 0,
                 "light_dirs": np.zeros((3, 3), np.float32),
                 "light_colors": np.zeros((3, 3), np.float32),
                 "ambient": np.ones(3, np.float32)}
        self.lighting = p
        self._bg_cache = {}

    def _fit_fov(self):
        """默认视角与 PS2 浏览器的大小接近；图标在默认视角下会出框时才放宽。

        把所有变形形状在一圈 16 个角度下的顶点投影到屏幕，取最大的超出量来算。"""
        pts = self.shapes.reshape(-1, 3)
        tan_half = math.tan(_FOV / 2)
        extent = 0.0
        for k in range(16):
            a = 2 * math.pi * k / 16
            x = pts[:, 0] * math.cos(a) + pts[:, 2] * math.sin(a)
            z = -pts[:, 0] * math.sin(a) + pts[:, 2] * math.cos(a)
            d = np.maximum(_CAMERA_Z - z, 0.1)
            ndc = np.maximum(np.abs(x), np.abs(pts[:, 1] - 2.5)) / d / tan_half
            extent = max(extent, float(ndc.max()))
        limit = 0.95  # 留一点边
        if extent <= limit:
            return _FOV
        return min(2 * math.atan(tan_half * extent / limit), math.radians(120.0))

    @property
    def animated(self):
        return self.duration > 0 and len(self.shapes) > 1 and bool(self.frames)

    def _shape_weights(self, seconds):
        """与 MyMC++ 的 _write_animated_vertices 相同的关键帧插值。"""
        w = np.zeros(len(self.shapes), dtype=np.float32)
        if not self.animated:
            w[0] = 1.0
            return w
        d = self.duration
        t = (seconds * _ANIM_FPS * self.anim_speed) % d
        for shape_id, keys in self.frames:
            last = nxt = None
            last_t = nxt_t = 0.0
            for kt, kv in keys:
                a = kt if kt <= t else kt - d
                if last is None or a > last_t:
                    last, last_t = kv, a
                b = kt if kt >= t else kt + d
                if nxt is None or b < nxt_t:
                    nxt, nxt_t = kv, b
            prog = (t - last_t) / (nxt_t - last_t) if nxt_t > last_t else 0.0
            w[shape_id] = (1.0 - prog) * last + prog * nxt
        total = w.sum()
        if total <= 0:
            w[:] = 0
            w[0] = 1.0
        else:
            w /= total
        return w

    def _background(self, size):
        bg = self._bg_cache.get(size)
        if bg is None:
            c = self.lighting["bg"]  # 0 左上, 1 右上, 2 左下, 3 右下
            y = np.linspace(0, 1, size, dtype=np.float32)[:, None, None]
            x = np.linspace(0, 1, size, dtype=np.float32)[None, :, None]
            top = c[0] * (1 - x) + c[1] * x
            bottom = c[2] * (1 - x) + c[3] * x
            bg = self._bg_cache[size] = top * (1 - y) + bottom * y
        return bg

    def render(self, size, seconds=0.0, yaw=0.0):
        """渲染一帧，返回 (size, size, 3) 的 uint8 RGB 图像。"""
        img = self._background(size).copy()
        weights = self._shape_weights(seconds)
        pos = np.tensordot(weights, self.shapes, axes=1)

        cy, sy = math.cos(yaw), math.sin(yaw)
        rot = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
        pos = pos @ rot.T
        pos[:, 1] -= 2.5
        normals = self.normals @ rot.T

        lp = self.lighting
        lambert = np.maximum(normals @ lp["light_dirs"].T, 0.0)          # (N, 3 盏灯)
        light = lp["ambient"][None, :] + lambert @ lp["light_colors"]    # (N, RGB)
        shade = self.colors * light

        # 透视投影到屏幕
        depth = _CAMERA_Z - pos[:, 2]
        valid_v = depth > 0.1
        f = 1.0 / math.tan(self.fov / 2)
        inv_d = 1.0 / np.where(valid_v, depth, 1.0)
        sx = (pos[:, 0] * f * inv_d + 1.0) * 0.5 * size
        sy_ = (1.0 - pos[:, 1] * f * inv_d) * 0.5 * size

        tri = np.arange(len(pos)).reshape(-1, 3)
        x0, x1, x2 = sx[tri[:, 0]], sx[tri[:, 1]], sx[tri[:, 2]]
        y0, y1, y2 = sy_[tri[:, 0]], sy_[tri[:, 1]], sy_[tri[:, 2]]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        # 屏幕 Y 向下，GL 的逆时针正面在这里面积为负；背面剔除
        keep = (area < -1e-9) & valid_v[tri].all(axis=1)
        if not keep.any():
            return self._to_uint8(img)
        tri, area = tri[keep], area[keep]
        x0, x1, x2, y0, y1, y2 = x0[keep], x1[keep], x2[keep], y0[keep], y1[keep], y2[keep]

        bx0 = np.clip(np.floor(np.minimum(np.minimum(x0, x1), x2)), 0, size).astype(np.int64)
        bx1 = np.clip(np.ceil(np.maximum(np.maximum(x0, x1), x2)), 0, size).astype(np.int64)
        by0 = np.clip(np.floor(np.minimum(np.minimum(y0, y1), y2)), 0, size).astype(np.int64)
        by1 = np.clip(np.ceil(np.maximum(np.maximum(y0, y1), y2)), 0, size).astype(np.int64)
        bw, bh = bx1 - bx0, by1 - by0
        counts = bw * bh
        ok = counts > 0
        if not ok.any():
            return self._to_uint8(img)
        idx_t = np.nonzero(ok)[0]
        counts = counts[ok]

        # 把所有三角形包围盒里的像素摊平成一维，一次性算重心坐标
        t_of = np.repeat(idx_t, counts)
        start = np.repeat(np.cumsum(counts) - counts, counts)
        local = np.arange(t_of.size) - start
        px = bx0[t_of] + local % bw[t_of] + 0.5
        py = by0[t_of] + local // bw[t_of] + 0.5

        a = area[t_of]
        w0 = ((x1[t_of] - px) * (y2[t_of] - py) - (x2[t_of] - px) * (y1[t_of] - py)) / a
        w1 = ((x2[t_of] - px) * (y0[t_of] - py) - (x0[t_of] - px) * (y2[t_of] - py)) / a
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            return self._to_uint8(img)
        t_of, px, py = t_of[inside], px[inside], py[inside]
        w = np.stack([w0[inside], w1[inside], w2[inside]], axis=1)

        vi = tri[t_of]                                   # (P, 3) 顶点下标
        pw = w * inv_d[vi]                               # 透视校正
        z = 1.0 / pw.sum(axis=1)
        pw *= z[:, None]

        # 深度测试：每个像素只留最近的
        pix = py.astype(np.int64) * size + px.astype(np.int64)
        order = np.lexsort((z, pix))
        pix_sorted = pix[order]
        first = np.ones(len(order), dtype=bool)
        first[1:] = pix_sorted[1:] != pix_sorted[:-1]
        win = order[first]
        pix, pw, vi = pix[win], pw[win], vi[win]

        color = np.einsum("pk,pkc->pc", pw, shade[vi])
        if self.texture is not None:
            uv = np.einsum("pk,pkc->pc", pw, self.uv[vi])
            tw, th = self.texture.shape[1], self.texture.shape[0]
            tx = np.clip((uv[:, 0] * tw).astype(np.int64), 0, tw - 1)
            ty = np.clip((uv[:, 1] * th).astype(np.int64), 0, th - 1)
            color = color * self.texture[ty, tx]
        img.reshape(-1, 3)[pix] = color
        return self._to_uint8(img)

    @staticmethod
    def _to_uint8(img):
        return (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def to_ppm(rgb):
    """RGB 图像 -> 二进制 PPM，可直接给 tkinter.PhotoImage(data=...)。"""
    h, w = rgb.shape[:2]
    return b"P6 %d %d 255\n" % (w, h) + rgb.tobytes()
