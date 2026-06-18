"""
slicing_functions.py

版权信息：2025 年 Daniel Brogan。

本文件来源于 Fractal Cortex 项目。Fractal Cortex 是一个面向多方向五轴
FDM 打印的切片器。本仓库在迁移该算法时保留了原始流程，便于后续与
参考实现比较切片行为。

许可说明：本程序按照 GNU General Public License 发布，可以依据 GPL
第 3 版或更新版本继续分发和修改。

程序按现状提供，
不附带适销性或特定用途适用性的保证。
完整许可文本请参考 GNU General Public License。

许可地址：<https://www.gnu.org/licenses/>。
"""

import trimesh
from trimesh import load_path
import numpy as np
from shapely.geometry import (
    LineString,
    MultiLineString,
    Point,
    Polygon,
    MultiPolygon,
    LinearRing,
    GeometryCollection
)
from shapely.geometry.polygon import orient
from shapely.validation import make_valid
from shapely.plotting import plot_polygon, plot_line
from shapely import affinity
from shapely.prepared import prep
from shapely.ops import unary_union
import time
import concurrent.futures
from operator import add
import os
import warnings
import sys

"""
本模块集中保存三轴和五轴切片的主要几何计算。

维护者说明：
    这里是算法兼容层。迁移后的 Fractal Cortex 流程仍然集中放在这个
    文件内，目的是让当前项目可以和参考实现逐步比对行为。更适合新代
    码调用的稳定入口位于 `core.settings`、`core.slicer` 和 `core.gcode`，
    后续界面和自动化脚本应优先通过这些封装进入算法。

    本文件的数据契约主要是固定顺序列表和嵌套的 Shapely 路径结构。
    修改函数前，应先确认函数处于哪个阶段：

    1. 网格切面：把 Trimesh 三维网格切成二维层截面；
    2. 外壳生成：把层多边形向内偏置，得到可打印的外壁路径；
    3. 区域分类：把层内区域分成实心填充区域和稀疏填充区域；
    4. 填充路径生成：用填充线与区域求交，得到喷头实际走线；
    5. 预览转换：把二维层路径映射回三维顶点，供 OpenGL 显示；
    6. G-code 写出：把路径序列转成打印机运动命令。

    该文件牵涉几何容错、并行计算和旧数据结构。改动时应尽量缩小范围，
    并配合小型可复现模型复核行为。
"""

# 本文件尽量贴近原始算法，便于观察迁移前后的几何行为是否一致。外围
# 模块负责提供类型化参数和更清楚的入口，本模块专注于多边形流水线：
# 先切出层截面，再生成外壳，随后区分稀疏与实心填充区域，最后优化
# 路径并写出 G-code。

# 默认填充类型和构建半径。当前 UI 默认只启用三角形填充。
infillType = "Triangular"
buildRadius = 150.0  # 单位为 mm，表示生成填充辅助线时覆盖的圆形构建区域半径。

# 旧版 printSettings 的索引契约。`settings.py` 中的
# `PrintSettings.to_legacy_list()` 必须和这张表保持一致，否则界面参数会
# 传错位置，进而影响切片或 G-code 写出。
#
#  0 喷嘴正常打印温度，单位为摄氏度。
#  1 首层喷嘴温度，单位为摄氏度。
#  2 热床正常打印温度，单位为摄氏度。
#  3 首层热床温度，单位为摄氏度。
#  4 填充百分比，UI 中使用 0 到 100。
#  5 外壳圈数，也就是每层外壁路径数量。
#  6 层高，单位为 mm。
#  7 正常打印速度，单位为 mm/s。
#  8 首层打印速度，单位为 mm/s。
#  9 正常空驶速度，单位为 mm/s。
# 10 首层空驶速度，单位为 mm/s。
# 11 空驶移动时是否启用 Z hop 抬升。
# 12 空驶移动时是否启用耗材回抽。
# 13 回抽距离，单位为 mm。
# 14 回抽速度，单位为 mm/s。
# 15 是否启用支撑，当前界面预留该项，算法主体尚未生成支撑。
# 16 是否启用边裙。
# 17 第一个联动旋转轴在 G-code 中使用的轴字。
# 18 第二个联动旋转轴在 G-code 中使用的轴字。


def _clean_linked_axis_symbol(value, default):
    """把用户输入的旋转轴名称整理成一个合法的 G-code 轴字。

    界面允许用户输入短文本，用来选择 A、B、C、U 等机床轴名。G-code
    运动命令中的轴字应当是单个大写英文字母，因此这里会去掉空格和非
    字母字符；如果用户没有填写内容，就使用默认轴字。
    """
    cleaned = "".join(char for char in str(value).strip().upper() if char.isalpha())
    return (cleaned or default)[0]


def _linked_axis_config(printSettings):
    """返回五轴联动时写入 G-code 的两个旋转轴轴字。

    轴字保存在 printSettings 的第 17 和第 18 项。早期调用方可能传入较
    短的列表，因此这里默认使用 A 与 B 保持兼容。如果两个输入最后变成
    同一个轴字，则自动调整第二个轴字，避免同一条 G-code 运动里出现
    重复地址。
    """
    axisA = _clean_linked_axis_symbol(printSettings[17], "A") if len(printSettings) > 17 else "A"
    axisB = _clean_linked_axis_symbol(printSettings[18], "B") if len(printSettings) > 18 else "B"
    if axisA == axisB:
        axisB = "B" if axisA != "B" else "A"
    return {
        "axisA": axisA,
        "axisB": axisB,
        "axisPair": axisA + " & " + axisB,
    }


def _format_gcode_number(value, precision=5):
    """把浮点数格式化成适合写入 G-code 的紧凑文本。

    输出时会先按固定精度四舍五入，再去掉多余的末尾零。这样既方便人工
    阅读，也能让文件比对得到稳定结果。极小的负零会归一化为 `0`。
    """
    number = round(float(value), precision)
    if number == 0:
        number = 0.0
    text = f"{number:.{precision}f}".rstrip("0").rstrip(".")
    return text or "0"


def _linked_axis_words(linkedAxis, axis_a_degrees, axis_b_degrees):
    """拼出类似 ` A90 B75` 的联动旋转轴片段。

    返回值开头保留一个空格，是因为调用方会把这段文本直接接在 G1 命令
    的 X、Y、Z 坐标之后。
    """
    return (
        " "
        + linkedAxis["axisA"]
        + _format_gcode_number(axis_a_degrees)
        + " "
        + linkedAxis["axisB"]
        + _format_gcode_number(axis_b_degrees)
    )


# 以下函数按切片流水线顺序组织：先切层，再生成外壳和填充，最后写出或预览。
def slicing_function(mesh, z):
    """返回三轴模式下一层水平截面。

    三轴切片始终使用垂直于构建平台的平面切模型。`z` 是切面在模型坐标
    系中的绝对高度。
    """
    output = mesh.section_multiplane(plane_normal=[0, 0, 1], plane_origin=[0, 0, z], heights=[0])
    return output[0]

def slicing_function_5_axis(mesh, normal, start, z):
    """返回五轴模式中某个 chunk 的一层任意方向截面。

    `start` 是该 chunk 基准切片平面上的一点。`z` 是沿该平面法向的偏移
    距离，因此同一 chunk 内生成的层都和该 chunk 的局部打印方向平行。
    """
    output = mesh.section_multiplane(plane_normal=normal, plane_origin=start, heights=[z])
    return output[0]

def apply_slicing_function(args):
    """为 `ProcessPoolExecutor.map` 拆包三轴切片参数。

    Python 进程池每个任务只接收一个位置参数。这个包装函数允许调用方传入
    `(mesh, z)` 元组，避免子进程依赖模块级全局 mesh 状态。
    """
    mesh, z = args
    return slicing_function(mesh, z)

def apply_slicing_function_5_axis(args):
    """为 `ProcessPoolExecutor.map` 拆包五轴切片参数。"""
    mesh, normal, start, z = args
    return slicing_function_5_axis(mesh, normal, start, z)


def get_initial_shells_for_one_layer(shapely_polygons, lineWidth):
    """为单层生成第一圈可打印外壳偏置。

    打印时希望挤出线材的外边缘贴合 STL 边界。喷嘴走的是线材中心线，
    因此第一圈路径需要从模型边界向内偏移半个线宽。
    """
    initialShellPolygons = []
    shellPolyList = []
    for poly in shapely_polygons:  # 从未偏置的原始层多边形开始处理。
        bufferedPoly = poly.buffer(-lineWidth / 2.0, join_style=2)  # 向内偏移半个线宽，使挤出线材外缘尽量贴合模型外轮廓；join_style=2 使用尖角连接。
        initialShellPolygons.append(make_valid(bufferedPoly))       # 修复偏置后可能出现的无效多边形，再保存为第一圈外壳。
        del bufferedPoly                                            # 删除临时对象，降低多层并行切片时的内存占用。
    shellPolyList.append(initialShellPolygons)                      # 单层外壳列表的第一个元素就是第一圈偏置结果。
    return shellPolyList


def get_remaining_shells_for_one_layer(shellPolyList, lineWidth, shellThickness):
    """为单层继续生成内侧外壳偏置。

    `shellPolyList` 进入函数时已经包含第一圈外壳。后续每一圈都在上一圈
    基础上继续向内偏移一个完整线宽。最后一圈外壳包围的区域会作为
    `innerMostPolygons` 返回，后续填充区域计算会从这里开始。
    """
    volatilePolyList = []
    if shellThickness > 1:
        for shell in range(shellThickness - 1):                                     # 继续生成除第一圈之外的剩余外壳。
            for geometry in shellPolyList[shell]:
                if geometry.geom_type == "Polygon":
                    newBufferedPoly = geometry.buffer(-lineWidth, join_style=2)     # 在上一圈基础上再向内偏移一个线宽；尖角连接会影响角部形状和后续填充求交。
                    volatilePolyList.append(make_valid(newBufferedPoly))
                    del newBufferedPoly
                elif geometry.geom_type == "MultiPolygon":                          # 如果一圈外壳分裂成多个多边形，需要逐个处理。
                    for poly in geometry.geoms:
                        newBufferedPoly = geometry.buffer(-lineWidth, join_style=2)
                        volatilePolyList.append(make_valid(newBufferedPoly))
                        del newBufferedPoly
            shellPolyList.append(volatilePolyList.copy())                           # 本轮偏置完成后，将新外壳加入该层外壳列表。
            del volatilePolyList
            volatilePolyList = []
    innerMostPolygons = shellPolyList[-1]                                           # 最内侧外壳定义了可填充区域的边界。
    return shellPolyList, innerMostPolygons


def get_shell_rings_for_one_layer(shellPolyList):
    """从外壳多边形中提取 LinearRing 路径。

    G-code 写出阶段需要的是路径线，而不是带面积的多边形。本函数把外边界
    和孔洞边界都转成可打印的壳路径，同时跳过点数不足的退化环。
    """
    shellRingsList = []
    for shell in shellPolyList:                                         # 每一圈外壳都要拆成线环，方便后续按路径顺序写出。
        for geometry in shell:
            if geometry.geom_type == "Polygon":
                if len(geometry.exterior.coords) >= 4:                  # 闭合环至少需要 3 个不同顶点，Shapely 会重复首点作为闭合点，所以坐标数至少为 4。
                    shellRingsList.append(geometry.exterior)            # 提取多边形外边界作为外壳路径。
                for ring in range(len(geometry.interiors)):
                    if len(geometry.interiors[ring].coords) >= 4:
                        shellRingsList.append(geometry.interiors[ring]) # 提取孔洞边界，内部孔洞也需要打印外壳。
            elif geometry.geom_type == "MultiPolygon":
                for poly in geometry.geoms:
                    if poly.geom_type == "Polygon":
                        if len(poly.exterior.coords) >= 4:
                            shellRingsList.append(poly.exterior)
                        for ring in range(len(poly.interiors)):
                            if len(poly.interiors[ring].coords) >= 4:
                                shellRingsList.append(poly.interiors[ring])
    return shellRingsList


def get_shells_for_one_layer(shapely_polygons, lineWidth, shellThickness):
    """返回单层的填充边界多边形和可打印外壳线环。"""
    shellPolyList = get_initial_shells_for_one_layer(shapely_polygons, lineWidth)                                   # 先按半个线宽生成最外侧外壳。
    shellPolyList, innerMostPolygons = get_remaining_shells_for_one_layer(shellPolyList, lineWidth, shellThickness) # 继续生成内侧外壳，并拿到最内侧填充边界。
    shellRingsList = get_shell_rings_for_one_layer(shellPolyList)                                                   # 把外壳面积对象转成线环，后续可直接转 G-code。
    return innerMostPolygons, shellRingsList

def apply_get_shells_for_one_layer(args):
    """为 `ProcessPoolExecutor.map` 拆包单层外壳生成参数。"""
    shapely_polygons, lineWidth, shellThickness = args
    return get_shells_for_one_layer(shapely_polygons, lineWidth, shellThickness)

def create_brim(shapely_polygons, lineWidth, brim_lines):
    """围绕首层轮廓反复向外偏置，生成边裙路径。

    返回值是按偏置圈数分组的边裙线环列表。每组对应一次向外偏置得到的
    LinearRing。写 G-code 时会先打印这些路径，用于改善首层附着和喷嘴
    出料稳定性。
    """
    
    if not isinstance(shapely_polygons, list):  # 统一输入形态，单个多边形也转成列表处理。
        shapely_polygons = [shapely_polygons]
    
    flattened_polygons = []
    for poly in shapely_polygons:               # MultiPolygon 需要拆成独立 Polygon，避免后续偏置时层级过深。
        if isinstance(poly, MultiPolygon):
            flattened_polygons.extend(list(poly.geoms))
        else:
            flattened_polygons.append(poly)
    
    brim_ring_list = []
    current_polygons = flattened_polygons
    
    for i in range(brim_lines):                                     # 每次循环生成一圈新的边裙。
        brim_layer_rings = []
        brim_layer_polygons = []
        
        for poly in current_polygons:                               # 对当前边界里的每个多边形继续向外扩张。
            buffered_poly = poly.buffer(lineWidth, join_style=2)    # 每圈向外偏移一个线宽。
            
            buffered_poly = make_valid(buffered_poly)               # 修复偏置后产生的自交或其他无效几何。
            
            # 只收集外边界，边裙本身不需要处理内部孔洞。
            if isinstance(buffered_poly, MultiPolygon):             # 向外偏置后可能形成多个分离区域。
                for geom in buffered_poly.geoms:                    # 逐个提取分离区域的外边界。
                    brim_layer_rings.append(geom.exterior)
                    brim_layer_polygons.append(geom)
            else:
                brim_layer_rings.append(buffered_poly.exterior)
                brim_layer_polygons.append(buffered_poly)
        
        brim_ring_list.append(brim_layer_rings)                     # 保存当前这一圈边裙线环。
        current_polygons = brim_layer_polygons                      # 下一圈继续在当前偏置结果基础上向外扩张。
    return brim_ring_list

def fix_polygon_or_multipolygon_ring_orientation(geometry):
    """在面积运算前统一多边形环方向。

    Shapely 在外边界和孔洞方向一致时更容易得到稳定结果。偏置、并集和差
    集可能返回 Polygon、MultiPolygon 或 GeometryCollection，因此这里对
    常见几何类型做统一修正。
    """
    
    if geometry.geom_type == "Polygon":
        returnedGeometry = orient(geometry, sign=1.0)
    elif geometry.geom_type == "MultiPolygon":
        multiPolys = []
        for poly in geometry.geoms:
            multiPolys.append(orient(poly))
        returnedGeometry = MultiPolygon(multiPolys)

    elif geometry.geom_type == "GeometryCollection":
        if geometry.is_empty == False:
            for g in geometry.geoms:
                if g.geom_type == "Polygon":
                    returnedGeometry = orient(geometry, sign=1.0)
                elif geometry.geom_type == "MultiPolygon":
                    multiPolys = []
                    for poly in geometry.geoms:
                        multiPolys.append(orient(poly))
                    returnedGeometry = MultiPolygon(multiPolys)
        else:
            returnedGeometry = geometry
    else:
        returnedGeometry = geometry
    return returnedGeometry

def safe_unary_union(geometries, buffer_value=0.00001):
    """带保守修复策略地执行 `unary_union`。

    很小的 buffer 值常用于修复几乎重合的边、自接触边和轻微无效多边形。
    如果并集仍然失败，就逐个修复几何体并跳过无法修复的对象。返回空
    Polygon 比中断整次切片更稳妥，调用方可以继续处理后续层。
    """
    if not geometries:
        return Polygon([])
    try:                            # 先尝试常规 unary_union，多数正常截面都能直接成功。
        return unary_union(geometries).buffer(buffer_value)
    except Exception as e:
        try:                        # 如果常规并集失败，就先修复每个几何体，再重试并集。
            valid_geoms = []
            for geom in geometries:
                try:
                    valid_geom = make_valid(geom.buffer(buffer_value))
                    if valid_geom.is_valid and not valid_geom.is_empty:
                        valid_geoms.append(valid_geom)
                except Exception:   # 个别几何体无法修复时跳过，避免一个坏片段拖垮整层。
                    continue
            if not valid_geoms:     # 没有任何可用几何体时返回空多边形，让调用方自然得到空路径。
                return Polygon([])
                
            return unary_union(valid_geoms)
        except Exception as e:      # 修复后仍失败时记录原因，并返回空多边形。
            print(f"Failed to create valid geometry: {e}")
            return Polygon([])

def get_manifold_areas_for_one_chunk(innerMostPolygonsList, infillPercentage, shellThickness):
    """计算一个 chunk 内每层的实心填充区域和内部稀疏填充区域。

    三轴模式下，一个 chunk 就是整个 STL。五轴模式下，一个 chunk 是相邻
    切片平面之间分出来的模型体积。这里的 manifold area 指需要 100%
    实心填充的区域，例如上表面、下表面、悬垂和欠悬垂附近需要加厚的
    局部区域。若用户设置 100% 填充，则每层最内侧外壳包围的所有面积
    都会被归入实心填充区域。若用户设置 0 到 100 之间的填充率，则先
    识别外表面附近必须实心的区域，剩余面积再交给稀疏填充。
    """

    # 相邻层之间的重叠关系决定了哪些地方需要实心支撑，哪些地方可以使用稀疏填充。

    def build_up_exposed_layers(exposedLayer, layerOverlapArea):
        """沿层方向加厚暴露区域，使外表面附近有足够实心材料。

        `exposedLayer` 表示暴露区域属于当前层还是上一层。`layerOverlapArea`
        是上层底面暴露面积或当前层顶面暴露面积。函数会沿相邻层继续把
        同一局部区域标记为实心填充，厚度由 shellThickness 控制。
        """
        
        if exposedLayer == "Current_Layer":
            sign = -1
            indexAddition = 0
        elif exposedLayer == "Upper_Layer":
            sign = 1
            indexAddition = 1
        for k in range(1, shellThickness):                                      # 按外壳厚度继续检查相邻层。
            nextLayerIndex = layer + sign*k + indexAddition                     # 当前层暴露时向下找层，上层暴露时向上找层。
            nextLayerArea = unary_union(innerMostPolygonsList[nextLayerIndex])  # 合并目标层多边形，便于与暴露区域求交。
            try:
                nextIntersection = layerOverlapArea.intersection(nextLayerArea) # 取暴露区域与相邻层的交集，得到需要继续加厚的局部面积。
            except:                                                             # 求交失败时保守处理，把整层目标区域标记为实心。
                nextIntersection = nextLayerArea
            if (nextIntersection.is_empty == False) and (nextIntersection.geom_type == "Polygon" or nextIntersection.geom_type == "MultiPolygon"): # 有有效交集时，把该交集加入目标层实心区域。
                manifoldAreas[nextLayerIndex].append(nextIntersection)
            elif nextIntersection.geom_type == "GeometryCollection":
                for geometry in nextIntersection.geoms:
                    if (geometry.geom_type == "Polygon" or geometry.geom_type == "MultiPolygon"):
                        manifoldAreas[nextLayerIndex].append(geometry)

    def get_upperLayerOverhangArea():  # 上层悬垂区域，也就是上层底面没有被当前层支撑的部分。
        """返回上一层相对于当前层的底面暴露区域。"""
        try:
            if currentLayerArea.intersects(upperLayerArea):
                upperLayerOverhangArea = unary_union(upperLayerArea.difference(currentLayerArea))
            else:   # 两层完全不相交时，上层底面整体都视为暴露。
                upperLayerOverhangArea = upperLayerArea
        except:     # 几何差集失败时保守处理，把整个上层区域作为实心候选。
            upperLayerOverhangArea = upperLayerArea
        return upperLayerOverhangArea

    def get_currentLayerUnderHangArea():  # 当前层欠悬垂区域，也就是当前层顶面没有被上一层覆盖的部分。
        """返回当前层相对于上一层的顶面暴露区域。"""
        try:
            if currentLayerArea.intersects(upperLayerArea):
                currentLayerUnderHangArea = unary_union(currentLayerArea.difference(upperLayerArea))
            else:                           # 两层完全不相交时，当前层顶面整体都视为暴露。
                currentLayerUnderHangArea = currentLayerArea
        except:                             # 几何差集失败时保守处理，把整个当前层区域作为实心候选。
            currentLayerUnderHangArea = currentLayerArea
        return currentLayerUnderHangArea

    manifoldAreas = {}
    for key in range(len(slice_levels)):    # 初始化实心填充区域字典，键是层号，值是该层需要 100% 填充的面积列表。
        manifoldAreas[key] = []

    internalAreas = {}
    for key in range(len(slice_levels)):    # 初始化内部稀疏填充区域字典，键是层号，值是该层稀疏填充面积列表。
        internalAreas[key] = []

    warnings.filterwarnings("error")        # 把几何库警告提升为异常，便于进入保守容错分支。

    if infillPercentage >= 1.0:
        """填充率为 100% 时，所有有面积的层都直接归入实心填充。"""
        for layer in range(len(slice_levels)):
            currentLayerArea = fix_polygon_or_multipolygon_ring_orientation(unary_union(innerMostPolygonsList[layer]))  # 统一外边界和孔洞方向，减少后续面积运算异常。
            if currentLayerArea.is_empty == False:                                                                      # 该层有有效面积时，整层作为实心填充区域。
                manifoldAreas[layer].append(currentLayerArea)

    elif infillPercentage >= 0.0 and infillPercentage < 1.0:
        """填充率位于 0% 到 100% 之间时，需要分别计算实心区域和稀疏区域。"""
        for layer in range(len(slice_levels)):
            currentLayerArea = fix_polygon_or_multipolygon_ring_orientation(unary_union(innerMostPolygonsList[layer]))

            """chunk 底部若干层：这些层需要直接作为实心底面。"""
            if layer < shellThickness:
                if currentLayerArea.is_empty == False:
                    manifoldAreas[layer].append(currentLayerArea)
                upperLayerArea = fix_polygon_or_multipolygon_ring_orientation(unary_union(innerMostPolygonsList[layer + 1]))
                upperLayerOverhangArea = get_upperLayerOverhangArea()               # 计算上一层底面相对当前层的暴露区域。
                if upperLayerOverhangArea.is_empty == False:                        # 若上一层底面有暴露面积，则该局部需要实心填充。
                    manifoldAreas[layer + 1].append(upperLayerOverhangArea)
                    build_up_exposed_layers("Upper_Layer", upperLayerOverhangArea)  # 沿层方向加厚该局部表面，使实心厚度达到外壳厚度要求。

                """chunk 中间层：通过上下层差异找出局部暴露区域。"""
            elif layer >= shellThickness and layer < len(slice_levels) - shellThickness:
                upperLayerArea = fix_polygon_or_multipolygon_ring_orientation(unary_union(innerMostPolygonsList[layer + 1]))
                currentLayerUnderHangArea = get_currentLayerUnderHangArea()
                upperLayerOverhangArea = get_upperLayerOverhangArea()

                if currentLayerArea.is_empty == False and upperLayerArea.is_empty == False:     # 当前层和上一层都有可填充区域时，需要比较两层差异。
                    if currentLayerUnderHangArea.is_empty == False:                             # 当前层顶面有暴露时，将该部分加入实心区域并加厚。
                        manifoldAreas[layer].append(currentLayerUnderHangArea)
                        build_up_exposed_layers("Current_Layer", currentLayerUnderHangArea)
                    if upperLayerOverhangArea.is_empty == False:                                # 上一层底面有暴露时，将该部分加入实心区域并加厚。
                        manifoldAreas[layer + 1].append(upperLayerOverhangArea)
                        build_up_exposed_layers("Upper_Layer", upperLayerOverhangArea)

                elif currentLayerArea.is_empty == False and upperLayerArea.is_empty == True:    # 当前层有面积而上一层没有面积，说明当前层顶面整体暴露。
                    manifoldAreas[layer].append(currentLayerArea)
                    currentLayerUnderHangArea = currentLayerArea                                # 整个当前层区域作为需要加厚的实心候选。
                    build_up_exposed_layers("Current_Layer", currentLayerUnderHangArea)

                elif currentLayerArea.is_empty == True and upperLayerArea.is_empty == False:    # 当前层没有面积而上一层有面积，说明上一层底面整体悬空。
                    manifoldAreas[layer + 1].append(upperLayerArea)
                    upperLayerOverhangArea = upperLayerArea                                     # 整个上一层区域作为需要加厚的实心候选。
                    build_up_exposed_layers("Upper_Layer", upperLayerOverhangArea)

                """接近 chunk 顶部的层：顶面区域逐步归入实心填充。"""
            elif layer >= shellThickness and layer < len(slice_levels) - 1:
                if currentLayerArea.is_empty == False:
                    manifoldAreas[layer].append(currentLayerArea)
                upperLayerArea = fix_polygon_or_multipolygon_ring_orientation(unary_union(innerMostPolygonsList[layer + 1]))
                currentLayerUnderHangArea = get_currentLayerUnderHangArea()
                if currentLayerUnderHangArea.is_empty == False:                                 # 当前层顶面有暴露时，加入实心区域并加厚。
                    manifoldAreas[layer].append(currentLayerUnderHangArea)
                    build_up_exposed_layers("Current_Layer", currentLayerUnderHangArea)

                """chunk 最顶层：只要有面积，通常都需要作为实心顶面。"""
            elif layer == len(slice_levels) - 1:
                if currentLayerArea.is_empty == False:                                          # 最顶层有有效面积时，整层加入实心区域并向下加厚。
                    manifoldAreas[layer].append(currentLayerArea)
                    currentLayerUnderHangArea = currentLayerArea
                    build_up_exposed_layers("Current_Layer", currentLayerUnderHangArea)

        """计算内部稀疏填充区域，也就是每层扣除实心区域后剩余的可填充面积。"""
        if infillPercentage != 0:
            """填充率为 0% 时保持空列表；其它情况继续生成稀疏填充候选区域。"""
            for layer in range(len(slice_levels)):
                try:
                    currentLayerArea = fix_polygon_or_multipolygon_ring_orientation(safe_unary_union(innerMostPolygonsList[layer])).buffer(0.00001)
                    if len(manifoldAreas[layer]) > 0:                                                                   # 该层已有实心区域时，稀疏填充区域等于当前层面积减去实心面积。
                        combinedManifoldArea = safe_unary_union(manifoldAreas[layer])                                   # 合并该层所有实心区域，便于一次差集运算。
                        if currentLayerArea.equals_exact(combinedManifoldArea, tolerance=0.001):                        # 实心区域近似等于整层面积时，该层没有稀疏填充。
                            pass
                        else:                                                                                           # 剩余面积就是内部稀疏填充区域。
                            try:
                                difference_result = currentLayerArea.buffer(0.00001).difference(combinedManifoldArea)   # 通过差集扣除实心区域。
                                if not difference_result.is_empty and difference_result.is_valid:                       # 差集结果有效且非空时才加入稀疏填充。
                                    internalAreas[layer].append(difference_result)
                            except Exception as e:
                                print("1. Error Processing Layer", str(layer), str(e))
                    else:                                                                                               # 该层没有实心区域时，整层最内侧面积都可作为稀疏填充区域。
                        internalAreas[layer].append(currentLayerArea)
                except Exception as e:                                                                                  # 面积运算异常时跳过该层，让后续层继续处理。
                    print("2. Error Processing Layer", str(layer), str(e))

    warnings.resetwarnings()                                                                                            # 恢复 warnings 默认行为，避免影响模块外的代码。
    return manifoldAreas, internalAreas


def define_alternating_infill_hatches_once(buildRadius, lineWidth):
    """预生成每层交替使用的 +45 度和 -45 度实心填充线。

    这些线用于 100% 实心填充区域，也用于顶面、底面和局部暴露区域。函数
    只生成一次构建平台范围内的长直线，后续每层通过与实际区域求交得到
    可打印线段。
    """
    buildRadius = float(buildRadius)                                        # 构建平台半径，单位为 mm。
    definedSpacing = lineWidth
    Ypositive = np.arange(definedSpacing, buildRadius, definedSpacing)
    Ynegative = -np.flip(Ypositive)
    Ycoords = np.concatenate((Ynegative, [0], Ypositive))
    buildAreaLines_0 = [LineString([(-buildRadius, y), (buildRadius, y)]) for y in Ycoords]                                 # 在构建平台范围内生成一组水平基础线。
    buildAreaLines_plus_45 = [affinity.rotate(k, 45, origin=Point(0, 0), use_radians=False) for k in buildAreaLines_0]      # 将基础线旋转到 +45 度方向。
    buildAreaLines_minus_45 = [affinity.rotate(k, 135, origin=Point(0, 0), use_radians=False) for k in buildAreaLines_0]    # 将基础线旋转到 -45 度等效方向。
    return buildAreaLines_plus_45, buildAreaLines_minus_45


def get_solid_infill_for_one_layer(layerNumber, solidArea, finalShellPoint, buildAreaLines_plus_45, buildAreaLines_minus_45, minInfillLineLength):
    """返回单层实心填充区域内的可打印填充线。"""

    # 实心填充在相邻层之间交叉排布，因此偶数层和奇数层使用不同方向的填充线。
    if layerNumber % 2 == 0:                        # 偶数层使用 +45 度填充线。
        buildAreaLines = buildAreaLines_plus_45
    else:                                           # 奇数层使用 -45 度填充线。
        buildAreaLines = buildAreaLines_minus_45

    layerInfills = [line.intersection(solidArea) for line in buildAreaLines if line.intersects(solidArea)]  # 用全局填充线与该层实心区域求交，得到落在区域内部的线段。

    infillLineStrings = clean_geometry_list_to_only_linestrings(layerInfills, minInfillLineLength)          # 清理求交结果，只保留足够长的 LineString。

    del layerInfills
    if infillLineStrings != []:
        results = get_infill_start_location_for_one_layer(infillLineStrings, finalShellPoint)               # 从离外壳结束点最近的填充线开始，减少空驶距离。
        firstLineIndex = results[0]
        firstLine = LineString(results[1])
        firstLineStartPoint = results[2]
        optimizedInfillPath = optimize_infill_paths_for_one_layer(firstLineIndex, firstLine, firstLineStartPoint, infillLineStrings)    # 用最近邻策略重排实心填充线顺序。
        del results
    else:                                                                                                   # 没有有效填充线时，该层实心填充路径为空。
        optimizedInfillPath = []
    return optimizedInfillPath


def apply_get_solid_infill_for_one_layer_function(args):
    """为并行计算拆包实心填充函数参数。"""
    layerNumber, solidArea, finalShellPoint, buildAreaLines_plus_45, buildAreaLines_minus_45, minInfillLineLength = args
    return get_solid_infill_for_one_layer(layerNumber, solidArea, finalShellPoint, buildAreaLines_plus_45, buildAreaLines_minus_45, minInfillLineLength)


def define_monolithic_infill_hatch_once(infillType, buildRadius, lineWidth, infillPercentage):
    """预生成稀疏填充使用的全局填充线。

    稀疏填充图案在 Z 方向不随层号变化，因此可先在构建区域内生成完整图案，
    后续每层只做求交。当前实现实际支持的是三角形填充。
    """
    buildRadius = float(buildRadius)                            # 构建平台半径，单位为 mm。
    if infillPercentage <= 0.0 or infillPercentage >= 1.0:      # 0% 和 100% 都不需要稀疏填充图案。
        buildAreaHatch = None
    elif infillType == "Triangular":                            # 生成全局三角形填充线。
        definedSpacing = round(3 * (lineWidth / infillPercentage), 3)
        Ypositive = np.arange(definedSpacing, buildRadius, definedSpacing)
        Ynegative = -np.flip(Ypositive)
        Ycoords = np.concatenate((Ynegative, [0], Ypositive))
        buildAreaLines_0 = [LineString([(-buildRadius, y), (buildRadius, y)]) for y in Ycoords]                         # 生成 0 度方向基础线。
        buildAreaLines_60 = [affinity.rotate(k, 60, origin=Point(0, 0), use_radians=False) for k in buildAreaLines_0]   # 复制基础线并旋转到 60 度。
        buildAreaLines_120 = [affinity.rotate(k, 120, origin=Point(0, 0), use_radians=False) for k in buildAreaLines_0] # 复制基础线并旋转到 120 度。
        buildAreaHatch = buildAreaLines_0 + buildAreaLines_60 + buildAreaLines_120                                      # 三个方向合并后形成三角形稀疏填充图案。
    elif infillType == "Grid":                                  # 网格填充预留入口，当前尚未实现。
        pass
    return buildAreaHatch


def get_internal_infill_for_one_layer(internalArea, finalShellPoint, buildAreaHatch, minInfillLineLength):
    """返回单层内部稀疏填充区域内的可打印填充线。"""
    
    layerInfills = [line.intersection(internalArea) for line in buildAreaHatch if line.intersects(internalArea)]    # 全局稀疏填充线与该层内部区域求交，得到实际可打印线段。
    infillLineStrings = clean_geometry_list_to_only_linestrings(layerInfills, minInfillLineLength)                  # 过滤出可用 LineString，并丢弃过短线段。
    del layerInfills
    if infillLineStrings != []:                                                                                     # 有有效稀疏填充线时继续优化走线顺序。
        results = get_infill_start_location_for_one_layer(infillLineStrings, finalShellPoint)                       # 从离外壳结束点最近的线段开始打印。
        firstLineIndex = results[0]
        firstLine = LineString(results[1])
        firstLineStartPoint = results[2]
        optimizedInfillPath = optimize_infill_paths_for_one_layer(firstLineIndex, firstLine, firstLineStartPoint, infillLineStrings) # 用最近邻策略重排内部填充线。
        del results
    else:                                                                                                           # 没有有效线段时，该层内部填充路径为空。
        optimizedInfillPath = []
    return optimizedInfillPath


def apply_get_internal_infill_for_one_layer_function(args):
    """为并行计算拆包内部填充函数参数。"""
    internalArea, finalShellPoint, buildAreaHatch, minInfillLineLength = args
    return get_internal_infill_for_one_layer(internalArea, finalShellPoint, buildAreaHatch, minInfillLineLength)


def clean_geometry_list_to_only_linestrings(geometryList, minInfillLineLength):
    """从求交结果中筛出可打印的 LineString。

    Shapely 求交可能返回 LineString、MultiLineString、GeometryCollection 或
    空对象。本函数把能打印的线段摊平成列表，并按最小长度过滤掉意义不大
    的短线段。
    """

    lineStringsOnlyList = []
    for element in geometryList:
        geometry = element[0]
        if geometry.is_empty == False:
            if geometry.geom_type == "LineString" and geometry.length > minInfillLineLength:    # 过短线段会增加打印时间且对强度帮助很小，因此直接丢弃。
                lineStringsOnlyList.append(geometry)
            elif geometry.geom_type == "MultiLineString":
                for g in geometry.geoms:
                    if g.geom_type == "LineString" and g.is_empty == False:
                        if g.length > minInfillLineLength:
                            lineStringsOnlyList.append(g)
            elif geometry.geom_type == "GeometryCollection":
                for g in geometry.geoms:
                    if g.geom_type == "LineString" and g.is_empty == False:
                        if g.length > minInfillLineLength:
                            lineStringsOnlyList.append(g)
                    elif geometry.geom_type == "MultiLineString":
                        for g in geometry.geoms:
                            if g.geom_type == "LineString" and g.is_empty == False:
                                if g.length > minInfillLineLength:
                                    lineStringsOnlyList.append(g)
    return lineStringsOnlyList


def get_infill_start_location_for_one_layer(infillLineStrings, finalShellPoint):
    """根据外壳结束位置选择该层填充路径的起始线和起始点。"""
    
    euclidianDistances = [finalShellPoint.distance(line) for line in infillLineStrings]             # 计算外壳结束点到每条填充线的距离。
    nearestLineIndex = np.argmin(euclidianDistances)                                                # 选择距离最短的线作为第一条填充线。
    del euclidianDistances
    nearestLine = list(infillLineStrings[nearestLineIndex].coords)                                  # 取出离外壳结束点最近的填充线。
    nearestLinePointDistances = [finalShellPoint.distance(Point(coord)) for coord in nearestLine]   # 比较该线两个端点到外壳结束点的距离。
    nearestLineNearestPointIndex = np.argmin(nearestLinePointDistances)                             # 选择更近的端点作为线段起点。
    del nearestLinePointDistances
    nearestLineNearestPoint = nearestLine[nearestLineNearestPointIndex]                             # 该点是填充开始点；若两端等距，numpy 会取第一个最小值。
    firstLineIndex = nearestLineIndex
    firstLine = nearestLine
    firstLineStartPoint = nearestLineNearestPoint
    return firstLineIndex, firstLine, firstLineStartPoint


def get_infill_start_locations_for_one_chunk(allLayerInfills_lineStrings, finalShellPoints):
    """为一个 chunk 内的每一层选择第一条填充线。

    每层都从靠近外壳结束点的填充线开始，减少外壳打印到填充打印之间的空驶。
    没有填充的层会填入占位值，以保持层号索引一致。
    """
    
    firstLineindices = []
    firstLines = []
    firstLineStartPoints = []
    for k in range(len(finalShellPoints)):
        if allLayerInfills_lineStrings[k] != []:
            results = get_infill_start_location_for_one_layer(allLayerInfills_lineStrings[k], finalShellPoints[k])
        else:
            results = [None, [], []]
        firstLineindices.append(results[0])
        firstLines.append(LineString(results[1]))
        firstLineStartPoints.append(results[2])
        del results
    return firstLineindices, firstLines, firstLineStartPoints


def optimize_infill_paths_for_one_layer(firstLineIndex, firstLine, firstLineStartPoint, infillLineStrings):
    """用最近邻启发式方法重排单层填充线段。

    算法先打印已选出的第一条线，然后每次从剩余线段中选择离上一条线尾端
    最近的线。每条线都会按较近端点作为起点来调整方向。该方法是局部
    启发式优化，计算量小，适合当前切片流水线。
    """
    
    firstLineEndPoint = list(firstLine.coords)
    firstLineEndPoint.remove(firstLineStartPoint)

    firstLineEndPoint = Point(firstLineEndPoint[0])
    visitedLineIndex = firstLineIndex
    previousTailPoint = firstLineEndPoint

    optimizedInfillPath = []
    optimizedInfillPath.append([LineString([firstLineStartPoint, list(firstLineEndPoint.coords)[0]])])      # 第一条线和方向已提前确定，先加入优化路径。
    for _ in range(len(infillLineStrings) - 1):                                                             # 继续处理剩余未访问填充线。
        infillLineStrings.pop(visitedLineIndex)                                                             # 从候选列表移除刚刚打印过的线。
        euclidianDistances = [previousTailPoint.distance(otherLine) for otherLine in infillLineStrings]     # 计算上一条线尾端到剩余线段的距离。
        nearestLineIndex = np.argmin(euclidianDistances)                                                    # 距离最小的线作为下一条打印线。
        del euclidianDistances
        nearestLine = list(infillLineStrings[nearestLineIndex].coords)                                      # 取出最近的下一条线。
        nearestLinePointDistances = [previousTailPoint.distance(Point(coord)) for coord in nearestLine]     # 比较该线两端到上一条线尾端的距离。
        nearestLineNearestPointIndex = np.argmin(nearestLinePointDistances)
        del nearestLinePointDistances
        nearestLineNearestPoint = nearestLine[nearestLineNearestPointIndex]                                 # 将更近端点作为下一条线的起点。
        if nearestLineNearestPointIndex == 0:                                                               # 若起点是第 0 个端点，则终点就是第 1 个端点。
            nearestLineFarthestPointIndex = 1
        else:
            nearestLineFarthestPointIndex = 0
        nearestLineFarthestPoint = nearestLine[nearestLineFarthestPointIndex]                               # 该端点作为下一条线的终点。
        optimizedInfillPath.append([LineString([nearestLineNearestPoint, nearestLineFarthestPoint])])       # 按确定方向加入优化后的路径。
        visitedLineIndex = nearestLineIndex
        previousTailPoint = Point(nearestLineFarthestPoint)                                                 # 保存当前尾端，供下一轮距离比较使用。
    return optimizedInfillPath


def get_3D_paths_for_one_layer(adhesion3D, layerTransform3D, shellRingsList, internalInfills, solidInfills):
    """把单层二维路径映射回三维空间，供预览渲染使用。

    Trimesh 切面结果包含二维多边形和 `to_3D` 变换矩阵。G-code 写出在部分
    场景可以直接使用二维路径，而 OpenGL 预览需要机床坐标下的三维顶点。
    """
    adhesionPath3D = []
    shellPath3D = []
    internalInfillPath3D = []
    solidInfillPath3D = []
    
    for adhesionRing in adhesion3D:
        adhesionPoly = Polygon(adhesionRing)
        adhesionPath2D = load_path(adhesionPoly)
        potentialPath3D = adhesionPath2D.to_3D(layerTransform3D)
        del adhesionPoly, adhesionPath2D
        if potentialPath3D.vertices.shape[1] == 3:  # 只接收真正转成三维坐标的路径。
            adhesionPath3D.append(potentialPath3D)
        del potentialPath3D
    for shellRing in shellRingsList:
        shellPoly = Polygon(shellRing)
        shellPath2D = load_path(shellPoly)
        potentialPath3D = shellPath2D.to_3D(layerTransform3D)
        del shellPoly, shellPath2D
        if potentialPath3D.vertices.shape[1] == 3:  # 只接收真正转成三维坐标的路径。
            shellPath3D.append(potentialPath3D)
        del potentialPath3D
    for infillLines in internalInfills:
        for geometry in infillLines:
            if geometry.geom_type == "LineString":
                infillPath2D = load_path(geometry.coords)
                try:
                    potentialPath3D = infillPath2D.to_3D(layerTransform3D)
                    del infillPath2D
                    if potentialPath3D.vertices.shape[1] == 3:  # 只接收真正转成三维坐标的路径。
                        internalInfillPath3D.append(potentialPath3D)
                    del potentialPath3D
                except:
                    pass
    for infillLines in solidInfills:
        for geometry in infillLines:
            if geometry.geom_type == "LineString":
                infillPath2D = load_path(geometry.coords)
                try:
                    potentialPath3D = infillPath2D.to_3D(layerTransform3D)
                    del infillPath2D
                    if potentialPath3D.vertices.shape[1] == 3:  # 只接收真正转成三维坐标的路径。
                        solidInfillPath3D.append(potentialPath3D)
                    del potentialPath3D
                except:
                    pass

    return adhesionPath3D, shellPath3D, internalInfillPath3D, solidInfillPath3D


def apply_get_3D_paths_for_one_layer_function(args):
    """为并行预览转换拆包单层路径参数。"""
    adhesion3D, layerTransform3D, shellRingsList, internalInfills, solidInfills = args
    return get_3D_paths_for_one_layer(adhesion3D, layerTransform3D, shellRingsList, internalInfills, solidInfills)


def all_calculations(mesh, printSettings):
    """执行完整三轴切片流程。

    输入：
        `mesh` 是已经应用用户平移、旋转和缩放后的 Trimesh 网格。
        `printSettings` 是文件顶部说明的旧版固定顺序参数列表。

    输出：
        返回五个按层号一一对应的数据结构：二维到三维的变换矩阵、边裙路径、
        外壳线环、内部稀疏填充路径和实心填充路径。GUI 预览和 G-code
        写出都依赖这个顺序。
    """

    # 先读取固定顺序参数。部分参数在几何阶段暂时不使用，但 G-code 写出
    # 阶段仍然需要它们，因此删除参数前必须同步检查 writer 函数和 UI。
    nozzleTemp = float(printSettings[0])
    initialNozzleTemp = float(printSettings[1])
    bedTemp = float(printSettings[2])
    initialBedTemp = float(printSettings[3])
    infillPercentage = float(printSettings[4]) / 100.0
    shellThickness = int(printSettings[5])
    layerHeight = float(printSettings[6])
    lineWidth = float(layerHeight * 2.0)
    minInfillLineLength = lineWidth * 2.0 # 小于该长度的填充线不会写入 G-code，避免喷头执行对质量贡献很小的碎短移动。
    printSpeed = float(printSettings[7])
    initialPrintSpeed = float(printSettings[8])
    travelSpeed = float(printSettings[9])
    initialTravelSpeed = float(printSettings[10])
    enableZHop = bool(printSettings[11])
    enableRetraction = bool(printSettings[12])
    retractionDistance = float(printSettings[13])
    retractionSpeed = float(printSettings[14])
    enableSupports = bool(printSettings[15])
    enableBrim = bool(printSettings[16])

    # 预生成后续会反复引用的填充图案，避免每一层重复构造全局填充线。
    buildAreaLines_plus_45, buildAreaLines_minus_45 = define_alternating_infill_hatches_once(buildRadius, lineWidth)    # 生成实心填充使用的 +45 度和 -45 度交替线。
    buildAreaHatch = define_monolithic_infill_hatch_once(infillType, buildRadius, lineWidth, infillPercentage)          # 生成内部稀疏填充使用的全局图案。


    # 1) 计算所有水平切面。
    print("Starting timer for Mesh Sections (PARALLEL TASK)")
    start = time.time()
    argsList = zip([mesh]*len(slice_levels), slice_levels)                                                                      # 把每一层的 mesh 和 z 高度打包成进程池任务参数。
    with concurrent.futures.ProcessPoolExecutor(max_workers=workerBees) as executor:                                            # 并行计算多层截面，以降低大模型切片耗时。
        meshSections = list(executor.map(apply_slicing_function, argsList))
    shapely_polygons_list = [[Polygon(p) for p in layer.polygons_full] if layer is not None else [] for layer in meshSections]  # 每层截面多边形列表，空层用空列表占位。
    transform3DList = [layer.metadata["to_3D"] if layer is not None else np.array([]) for layer in meshSections]                # 每层二维截面回到三维空间所需的变换矩阵。
    del meshSections                                                                                                            # 后续只使用多边形和变换矩阵，及时释放原始截面对象。
    end = time.time() - start
    print("Mesh Sections took ", end, "seconds.", "\n")



    # 2) 计算每层所有外壳偏置。
    print("Starting timer for Shells (PARALLEL TASK)")
    start = time.time()
    argsList = zip(shapely_polygons_list, [lineWidth]*len(shapely_polygons_list), [shellThickness]*len(shapely_polygons_list))
    with concurrent.futures.ProcessPoolExecutor(max_workers=workerBees) as executor:
        innerMostPolygonsList, shellRingsListList = zip(*executor.map(apply_get_shells_for_one_layer, argsList))
    end = time.time() - start
    print("Shells took ", end, "seconds.", "\n")



    # 3) 比较相邻层重叠关系，区分实心填充区域和内部稀疏填充区域。
    print("Starting timer for Getting Manifold & Internal Areas (SERIES TASK)")                                                         # 该阶段依赖相邻层上下文，按顺序执行更容易保持逻辑清楚。
    start = time.time() 
    manifoldAreasDict, internalAreasDict = get_manifold_areas_for_one_chunk(innerMostPolygonsList, infillPercentage, shellThickness)    # 三轴模式下，一个 chunk 就是整个模型。
    del innerMostPolygonsList
    manifoldAreas = [[safe_unary_union(manifoldAreasDict[key])] for key in manifoldAreasDict]
    internalAreas = [[safe_unary_union(internalAreasDict[key])] for key in internalAreasDict]
    end = time.time() - start
    print("Getting Manifold & Internal Areas took ", end, "seconds.", "\n")



    # 4) 为所有层生成并优化内部稀疏填充路径。
    finalShellPoints = []                                                       # 每层外壳打印结束时的喷嘴位置，用于选择填充起点。
    lastNozzleLocation = (0.0, 0.0)                                             # 初始喷嘴位置；空层会沿用上一层有效位置。
    for k in range(len(shellRingsListList)):
        if shellRingsListList[k] == []:                                         # 该层没有外壳时，用上一层喷嘴位置作为填充起点参考。
            finalShellPoints.append(lastNozzleLocation)
        else:                                                                   # 该层有外壳时，外壳最后一个点就是进入填充前的位置。
            lastNozzleLocation = Point(shellRingsListList[k][-1].coords[-1])
            finalShellPoints.append(lastNozzleLocation)
    print("Starting timer for Internal Infill & Respective Path Optimization (PARALLEL)")
    start = time.time()
    if infillPercentage <= 0.0 or infillPercentage >= 1.0:                      # 0% 或 100% 填充都没有内部稀疏填充路径。
        optimizedInternalInfills = [[] for _ in range(len(slice_levels))]
    else:                                                                       # 中间填充率需要生成稀疏填充并优化喷头行走顺序。
        argsList = zip(internalAreas, finalShellPoints, [buildAreaHatch] * len(internalAreas), [minInfillLineLength] * len(internalAreas),)
        with concurrent.futures.ProcessPoolExecutor(max_workers=workerBees) as executor:
            optimizedInternalInfills = list(executor.map(apply_get_internal_infill_for_one_layer_function, argsList))
    del buildAreaHatch
    end = time.time() - start
    print("Internal Infill took ", end, "seconds.", "\n")



    # 5) 为所有层生成并优化实心填充路径。
    print("Starting timer for Manifold Infill & Respective Path Optimization (PARALLEL)")
    start = time.time()
    argsList = zip(layerNumbers, manifoldAreas, finalShellPoints, [buildAreaLines_plus_45]*len(layerNumbers), [buildAreaLines_minus_45]*len(layerNumbers), [minInfillLineLength]*len(layerNumbers))
    with concurrent.futures.ProcessPoolExecutor(max_workers=workerBees) as executor:
        optimizedSolidInfills = list(executor.map(apply_get_solid_infill_for_one_layer_function, argsList))
    del buildAreaLines_plus_45, buildAreaLines_minus_45
    end = time.time() - start
    print("Manifold Infill took ", end, "seconds.", "\n")



    # 6) 如果启用边裙，则只基于首层轮廓计算边裙。
    print("Starting timer for Adhesion")
    start = time.time()
    initialLayerPolygons = shapely_polygons_list[0]                         # 边裙只依赖首层轮廓。
    adhesionList = [[] for k in range(len(shellRingsListList))]             # 以层列表形式保存，便于预览和写出函数按层索引读取。
    if enableBrim == True:
        adhesionList[0] = create_brim(initialLayerPolygons, lineWidth, 4)   # 当前边裙圈数固定为 4，后续可扩展成 UI 参数。
    else:
        pass
    end = time.time() - start  #
    print("Adhesion calculations took ", end, "seconds.", "\n")

    return transform3DList, adhesionList, shellRingsListList, optimizedInternalInfills, optimizedSolidInfills

def all_5_axis_calculations(mesh, printSettings, slicingDirections):
    """执行完整五轴切片流程。

    五轴流程会先把用户定义的切片方向平面转换成模型 chunk。每个 chunk
    使用自己的局部法向单独切片。返回的变换矩阵、外壳和填充结果都以
    chunk 索引作为字典键，预览和 G-code 写出会按同一顺序重放。

    初始竖直 chunk 之后的 chunk 会执行床面与喷嘴碰撞检查。若发现风险
    过高的床面间隙，流程会在不安全 chunk 写出 G-code 之前停止。
    """
    global slice_levels

    # 读取标准打印参数。索引顺序必须和文件顶部的 printSettings 契约、
    # `all_calculations()` 以及两个 G-code 写出函数保持一致。
    nozzleTemp = float(printSettings[0])
    initialNozzleTemp = float(printSettings[1])
    bedTemp = float(printSettings[2])
    initialBedTemp = float(printSettings[3])
    infillPercentage = float(printSettings[4]) / 100.0
    shellThickness = int(printSettings[5])
    layerHeight = float(printSettings[6])
    lineWidth = float(layerHeight * 2.0)
    minInfillLineLength = lineWidth * 2.0    # 过滤过短填充线，避免生成无意义的碎短 G-code 运动。
    printSpeed = float(printSettings[7])
    initialPrintSpeed = float(printSettings[8])
    travelSpeed = float(printSettings[9])
    initialTravelSpeed = float(printSettings[10])
    enableZHop = bool(printSettings[11])
    enableRetraction = bool(printSettings[12])
    retractionDistance = float(printSettings[13])
    retractionSpeed = float(printSettings[14])
    enableSupports = bool(printSettings[15])
    enableBrim = bool(printSettings[16])
    # 读取五轴切片平面设置。
    numSlicingDirections = int(slicingDirections[0])
    startingPositions = slicingDirections[1]
    directions = slicingDirections[2]
    directionsRad = [np.radians(anglePair).tolist() for anglePair in directions]
    slicePlaneList = list(range(numSlicingDirections))
    reversedSlicePlaneList = slicePlaneList[::-1]
    # 预生成后续会反复引用的填充图案。
    buildAreaLines_plus_45, buildAreaLines_minus_45 = define_alternating_infill_hatches_once(buildRadius, lineWidth)    # 生成实心填充的交替方向线。
    buildAreaHatch = define_monolithic_infill_hatch_once(infillType, buildRadius, lineWidth, infillPercentage)          # 生成内部稀疏填充的全局图案。

    def spherical_to_normal(theta, phi):
        """把球坐标角度转换为三维法向量。"""
        
        # 输入角度来自 UI，单位是度；三角函数需要弧度。
        theta = theta*(np.pi/180.0)
        phi = phi*(np.pi/180.0)
        
        nx = np.sin(theta) * np.cos(phi)
        ny = np.sin(theta) * np.sin(phi)
        nz = np.cos(theta)
        return np.array([nx, ny, nz])
    
    def create_chunkList():
        """先按每个切片平面法向，取模型位于该平面前方的部分作为初始 chunk。"""
        
        chunkList = []
        for k in range(int(numSlicingDirections)):
            currentStart = startingPositions[k]
            currentNormal = spherical_to_normal(*directions[k])
            unprocessedChunk = mesh.slice_plane(currentStart, currentNormal, cap=True, face_index=None, cached_dots=None)
            chunkList.append(unprocessedChunk)
        """
        随后从后面的 chunk 往前逐个做差集，把更后续方向负责打印的材料从
        当前 chunk 中扣掉。这样每个 chunk 只保留自己负责的体积，有助于
        减少打印头和已打印零件之间的碰撞风险。
        """
        for k in slicePlaneList:
            remainingChunk = chunkList[k]
            for r in reversedSlicePlaneList:
                if r > k:
                    latterChunk = chunkList[r]
                    remainingChunk = remainingChunk.difference(latterChunk, check_volume=False)
            if remainingChunk.is_empty == False:
                chunkList[k] = remainingChunk
            else:
                chunkList[k] = None
        return chunkList

    def align_mesh_base_to_xy(mesh, base_point, base_normal):
        """把指定基准面旋转和平移到 Z=0 的 XY 平面上。"""
        
        # 把输入点和法向转成 numpy 数组，方便进行矩阵运算。
        base_point = np.array(base_point, dtype=float)
        base_normal = np.array(base_normal, dtype=float)
        
        # 法向量必须单位化，否则旋转轴和夹角计算会受长度影响。
        base_normal = base_normal / np.linalg.norm(base_normal)
        
        # 目标是把基准法向对齐到全局 Z 轴。
        z_axis = np.array([0, 0, 1])
        
        # 旋转轴由当前法向与 Z 轴叉乘得到。
        rotation_axis = np.cross(base_normal, z_axis)
        
        # 如果法向已经和 Z 轴平行，旋转轴接近零向量。
        if np.allclose(rotation_axis, 0):
            # 已经对齐时无需旋转，后续只需要平移。
            rotation_matrix = np.eye(3)
        else:
            # 常规情况使用轴角公式构造旋转矩阵。
            rotation_axis = rotation_axis / np.linalg.norm(rotation_axis)
            cos_angle = np.dot(base_normal, z_axis)
            angle = np.arccos(np.clip(cos_angle, -1.0, 1.0))
            
            K = np.array([
                [0, -rotation_axis[2], rotation_axis[1]],
                [rotation_axis[2], 0, -rotation_axis[0]],
                [-rotation_axis[1], rotation_axis[0], 0]
            ])
            rotation_matrix = np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * (K @ K)
        
        # 创建 4x4 齐次变换矩阵，先写入旋转部分。
        transform = np.eye(4)
        transform[:3, :3] = rotation_matrix
        
        # 复制网格后应用旋转，避免修改原始 chunk。
        rotated_mesh = mesh.copy()
        rotated_mesh.apply_transform(transform)
        
        # 旋转后计算基准点的 Z 坐标，用它决定需要平移多少才能落到 Z=0。
        rotated_point = rotation_matrix @ base_point
        z_offset = rotated_point[2]
        
        # 创建平移矩阵，把基准面移动到 Z=0。
        translation = np.eye(4)
        translation[2, 3] = -z_offset
        
        # 应用平移，得到局部坐标系下便于切片的网格。
        rotated_mesh.apply_transform(translation)
        
        # 合并旋转和平移矩阵，供后续把路径映射回全局坐标。
        final_transform = translation @ transform
        return rotated_mesh, final_transform

    def inverse_transform_chunks_to_get_respective_slice_levels():
        maxChunkZextents = {}
        chunk_slice_levels = {}
        for k in range(int(numSlicingDirections)):
            currentChunk = chunkList[k]
            if k == 0: # 初始切片方向已经是全局竖直方向，可直接读取 Z 范围。
                chunkBounds = currentChunk.bounds
                meshBottom = round(chunkBounds[0][2], 3)
                meshTop = round(chunkBounds[1][2], 3)
                if meshBottom <= 0:  # 模型底部在构建面以下或正好接触构建面时，从 Z=0 开始切。
                    z_extents = [0, meshTop]
                elif meshBottom > 0:  # 模型整体高于构建面时，从模型底部开始切。
                    z_extents = [meshBottom, meshTop]
                maxChunkZextents[str(k)] = z_extents
            else: # 后续 chunk 先对齐到局部 XY 平面，再读取局部 Z 范围。
                currentStart = startingPositions[k]
                currentNormal = spherical_to_normal(*directions[k])
                rotatedChunk = align_mesh_base_to_xy(currentChunk, currentStart, currentNormal)[0]
                chunkBounds = rotatedChunk.bounds
                meshBottom = round(chunkBounds[0][2], 3)
                meshTop = round(chunkBounds[1][2], 3)
                if meshBottom <= 0:  # 局部底面低于或接触构建面时，从局部 Z=0 开始切。
                    z_extents = [0, meshTop]
                elif meshBottom > 0:  # 局部底面高于构建面时，从 chunk 底部开始切。
                    z_extents = [meshBottom, meshTop]
                maxChunkZextents[str(k)] = z_extents


        for key in maxChunkZextents:
            current_z_extents = maxChunkZextents[key]
            current_z_levels = np.arange(*current_z_extents, step=layerHeight)  # 喷嘴目标高度序列。
            chunk_slice_levels[key] = [round(z - (layerHeight / 2), 5) for z in current_z_levels]  # 实际切面位于喷嘴目标高度下方半个层高处。
            del chunk_slice_levels[key][0]

        return chunk_slice_levels

    global stopSlicing
    stopSlicing = False
    def checkForBedNozzleCollisions(chunk, meshSections, transform3DList):
        global stopSlicing
        minAcceptableBedToNozzleClearance = 12.0
        paths_3D = []
        for layer, path2D in enumerate(meshSections): # 把二维截面路径转回三维，以便检查全局 Z 高度。
            currentTransform = transform3DList[layer]
            paths_3D.append(path2D.to_3D(currentTransform))
            
        sectionPoints = [path.vertices for path in paths_3D]
        sectionZValuesBySlicePlane = [[point[2] for point in section] for section in sectionPoints]

        for layer, section in enumerate(sectionZValuesBySlicePlane):
            theta = directionsRad[chunk][0]
            sinTheta = abs(np.sin(theta))
            for z in section:
                if stopSlicing == False:
                    if z <= minAcceptableBedToNozzleClearance and round(sinTheta, 5) != 0:
                        currentBedToNozzleDistance = abs(z) / sinTheta
                        if currentBedToNozzleDistance < minAcceptableBedToNozzleClearance: # 床面到喷嘴距离不足，判定存在碰撞风险。
                            stopSlicing = True
        return stopSlicing


    chunkList = create_chunkList()
    chunk_slice_levels = inverse_transform_chunks_to_get_respective_slice_levels()

    """
    每个 chunk 的切片高度已经确定，下面按 chunk 顺序分别执行切面、外壳、
    填充和边裙计算。
    """
    chunk_transform3DList = {}
    chunk_shellRingsListList = {}
    chunk_optimizedInternalInfills = {}
    chunk_optimizedSolidInfills = {}
    for k in range(int(numSlicingDirections)): # 逐个处理五轴打印方向对应的 chunk。
        # chunk 表示分配给某个打印方向的模型体积。每个 chunk 先在自己的
        # 局部方向下切片，预览或写 G-code 时再映射回机床坐标。
        print('__________________________________')
        print('Chunk #:', str(k))
        currentChunk = chunkList[k]
        currentStart = startingPositions[k]
        currentNormal = spherical_to_normal(*directions[k])
        slice_levels = chunk_slice_levels[str(k)]
        layerNumbers = list(range(len(slice_levels)))  # 当前 chunk 内部的层号索引。
        
        
        # 1) 计算当前 chunk 的所有局部切面。
        print("Starting timer for currentChunk Mesh Sections (PARALLEL)")
        start = time.time()
        argsList = zip([currentChunk]*len(slice_levels), [currentNormal]*len(slice_levels), [currentStart]*len(slice_levels), slice_levels)  # 为进程池打包参数，并显式重复 chunk，避免依赖全局 mesh。
        with concurrent.futures.ProcessPoolExecutor(max_workers=workerBees) as executor:
            meshSections = list(executor.map(apply_slicing_function_5_axis, argsList))
        shapely_polygons_list = [[Polygon(p) for p in layer.polygons_full] if layer is not None else [] for layer in meshSections]  # 将切面结果转成每层 Shapely 多边形。
        transform3DList = [layer.metadata["to_3D"] if layer is not None else np.array([]) for layer in meshSections]  # 保存每层二维截面回三维的变换矩阵。


        # 1.5) 非初始 chunk 需要检查床面与喷嘴是否可能碰撞。
        if k > 0: # 初始 chunk 为竖直方向，当前碰撞检查主要针对后续倾斜 chunk。
            checkForBedNozzleCollisions(k, meshSections, transform3DList)
        
        del meshSections
        end = time.time() - start
        print("Mesh Sections took ", end, "seconds.", "\n")
        chunk_transform3DList[str(k)] = transform3DList

        if stopSlicing == False:
            # 2) 计算当前 chunk 每层所有外壳偏置。
            print("Starting timer for Shells (PARALLEL)")
            start = time.time()
            argsList = zip(shapely_polygons_list, [lineWidth] * len(shapely_polygons_list), [shellThickness] * len(shapely_polygons_list),)
            with concurrent.futures.ProcessPoolExecutor(max_workers=workerBees) as executor:
                innerMostPolygonsList, shellRingsListList = zip(*executor.map(apply_get_shells_for_one_layer, argsList))
            end = time.time() - start
            print("Shells took ", end, "seconds.", "\n")
            chunk_shellRingsListList[str(k)] = shellRingsListList
            
            # 3) 比较当前 chunk 内相邻层重叠关系，区分实心和稀疏填充区域。
            print("Starting timer for Getting Manifold & Internal Areas (SERIES)")
            start = time.time()
            manifoldAreasDict, internalAreasDict = get_manifold_areas_for_one_chunk(innerMostPolygonsList, infillPercentage, shellThickness)
            del innerMostPolygonsList
            manifoldAreas = [[safe_unary_union(manifoldAreasDict[key])] for key in manifoldAreasDict]
            internalAreas = [[safe_unary_union(internalAreasDict[key])] for key in internalAreasDict]
            end = time.time() - start
            print("Getting Manifold & Internal Areas took ", end, "seconds.", "\n")

            # 4) 为当前 chunk 的所有层生成并优化内部稀疏填充路径。
            finalShellPoints = []  # 每层外壳打印结束时的喷嘴位置。
            lastNozzleLocation = (0.0, 0.0)  # 当前 chunk 内已知的上一个喷嘴位置。
            for c in range(len(shellRingsListList)):
                if shellRingsListList[c] == []:
                    finalShellPoints.append(lastNozzleLocation)
                else:
                    lastNozzleLocation = Point(shellRingsListList[c][-1].coords[-1])
                    finalShellPoints.append(lastNozzleLocation)
            print("Starting timer for Internal Infill & Respective Path Optimization (PARALLEL)")
            start = time.time()
            if infillPercentage <= 0.0 or infillPercentage >= 1.0:
                optimizedInternalInfills = [[] for _ in range(len(slice_levels))]
            else:
                argsList = zip(internalAreas, finalShellPoints, [buildAreaHatch] * len(internalAreas), [minInfillLineLength] * len(internalAreas),)
                with concurrent.futures.ProcessPoolExecutor(max_workers=workerBees) as executor:
                    optimizedInternalInfills = list(executor.map(apply_get_internal_infill_for_one_layer_function, argsList))
            end = time.time() - start
            print("Internal Infill took ", end, "seconds.", "\n")
            chunk_optimizedInternalInfills[str(k)] = optimizedInternalInfills

            # 5) 为当前 chunk 的所有层生成并优化实心填充路径。
            print("Starting timer for Manifold Infill & Respective Path Optimization (PARALLEL)")
            start = time.time()
            argsList = zip(layerNumbers, manifoldAreas, finalShellPoints, [buildAreaLines_plus_45] * len(layerNumbers), [buildAreaLines_minus_45] * len(layerNumbers), [minInfillLineLength] * len(layerNumbers))
            with concurrent.futures.ProcessPoolExecutor(max_workers=workerBees) as executor:
                optimizedSolidInfills = list(executor.map(apply_get_solid_infill_for_one_layer_function, argsList))
            end = time.time() - start
            print("Manifold Infill took ", end, "seconds.", "\n")
            chunk_optimizedSolidInfills[str(k)] = optimizedSolidInfills

            if k == 0: # 边裙只在初始 chunk 的首层打印一次。
                # 6) 如果启用边裙，则计算边裙路径。
                print("Starting timer for Adhesion")
                start = time.time()
                initialLayerPolygons = shapely_polygons_list[0]
                adhesionList = [[] for k in range(len(shellRingsListList))]
                if enableBrim == True:
                    adhesionList[0] = create_brim(initialLayerPolygons, lineWidth, 4)
                else:
                    pass
                end = time.time() - start
                print("Adhesion calculations took ", end, "seconds.", "\n")            
                
            print('__________________________________')
            print(' ')
        else:
            print('Slicing Stopped. Detected collision between bed and nozzle.')
            break
    
    return chunk_transform3DList, adhesionList, chunk_shellRingsListList, chunk_optimizedInternalInfills, chunk_optimizedSolidInfills


def export_mesh(importedMesh):  # 把 Trimesh 网格导出成可序列化字典。
    """把 Trimesh 对象导出为可序列化字典。"""
    return trimesh.exchange.export.export_dict(importedMesh)


def slice_in_3_axes(printSettings, meshData):
    """三轴切片的旧版公开入口。

    `meshData` 的结构是 `[loaded_indices, mesh_dict]`。其中
    `loaded_indices` 保存用户选中的模型编号，`mesh_dict` 用编号映射到
    Trimesh 对象。若用户同时选择多个模型，会先合并成一个网格，再交给
    后续算法统一切片。
    """
    global mesh, slice_levels, layerNumbers

    layerHeight = float(printSettings[6])

    numObjects = len(meshData[0])

    if numObjects > 1:  # 多个 STL 同时切片时先合并成一个网格，简化后续截面计算。
        print("Multiple STLs Input")
        importedMeshList = list(meshData[1].values())
        importedMergedMesh = trimesh.util.concatenate(importedMeshList)
        importedMesh = importedMergedMesh

    elif numObjects == 1:  # 单个 STL 直接取出对应网格。
        print("Slicing one STL")
        fileKey = meshData[0][0]
        importedMesh = meshData[1][fileKey]

    mesh = importedMesh.copy()  # 创建本地副本，便于并行进程安全地 pickle 和读取。

    meshBounds = mesh.bounds
    meshBottom = meshBounds[0][2]
    meshTop = meshBounds[1][2]

    if meshBottom <= 0:  # 模型底部在构建面以下或接触构建面时，从 Z=0 开始切。
        z_extents = [0, meshTop]
    elif meshBottom > 0:  # 模型底部高于构建面时，从模型底部开始切。
        z_extents = [meshBottom, meshTop]

    z_levels = np.arange(*z_extents, step=layerHeight)  # 喷嘴目标高度序列。

    slice_levels = [round(z - (layerHeight / 2), 5) for z in z_levels]  # 实际切面高度位于喷嘴目标高度下方半个层高处。
    print(str(len(slice_levels) - 1), "layers", "\n")
    del slice_levels[0]

    layerNumbers = list(range(len(slice_levels)))  # 层号索引，用于填充方向交替和结果按层存储。

    transform3DList, adhesionList, shellRingsListList, optimizedInternalInfills, optimizedSolidInfills = all_calculations(mesh, printSettings)

    return transform3DList, adhesionList, shellRingsListList, optimizedInternalInfills, optimizedSolidInfills

def slice_in_5_axes(printSettings, meshData, slicingDirections):
    """五轴切片的旧版公开入口。

    `slicingDirections` 的结构是 `[count, starting_positions, directions]`。
    `starting_positions` 是每个切片平面上的点，`directions` 是以度为单位
    的 `[theta, phi]` 角度对。真正的 chunk 分割和分 chunk 切片工作由
    `all_5_axis_calculations()` 执行。
    """
    global mesh, slice_levels, layerNumbers
    
    # 提取后续流程需要的层高和模型数量。
    layerHeight = float(printSettings[6])
    numObjects = len(meshData[0])


    if numObjects > 1:  # 多个 STL 同时切片时先合并成一个网格。
        print("Multiple STLs Input")
        importedMeshList = list(meshData[1].values())
        importedMergedMesh = trimesh.util.concatenate(importedMeshList)
        importedMesh = importedMergedMesh

    elif numObjects == 1:  # 单个 STL 直接取出对应网格。
        print("Slicing one STL")
        fileKey = meshData[0][0]
        importedMesh = meshData[1][fileKey]

    mesh = importedMesh.copy()  # 创建本地副本，便于并行进程安全地 pickle 和读取。

    chunk_transform3DList, adhesionList, chunk_shellRingsListList, chunk_optimizedInternalInfills, chunk_optimizedSolidInfills = all_5_axis_calculations(mesh, printSettings, slicingDirections)

    return chunk_transform3DList, adhesionList, chunk_shellRingsListList, chunk_optimizedInternalInfills, chunk_optimizedSolidInfills


def write_5_axis_gcode(newFile, savedFileName, printSettings, startingPositions, directions, chunk_transform3DList, adhesionList, chunk_shellRingsListList, chunk_optimizedInternalInfills, chunk_optimizedSolidInfills):
    """把五轴切片结果写出为 G-code 文件。

    写出内容包含普通 X、Y、Z、E 线性运动，以及由 `printSettings[17]` 和
    `printSettings[18]` 配置的两个联动旋转轴。chunk 相关数据结构用字符
    串形式的 chunk 索引作为键，这是上游五轴计算阶段的存储约定。
    """

    def transcribe_pathPoints_to_gcode(pathPoints, PRINT_FEEDRATE, runOnce, newChunk):
        """把一条可打印路径写成 G0/G1 运动命令。

        `runOnce` 表示当前特征在本层尚未写入初始空驶和打印进给设置。
        `newChunk` 表示刚切换到新的五轴 chunk，需要额外抬高喷嘴以降低
        旋转或重新定位时的碰撞风险。
        """
        global E, previousE

        for p in range(len(pathPoints)):
            point = pathPoints[p]
            X = round(point[0], 5)
            Y = round(point[1], 5)
            Z = round(point[2] + 0.5 * layerHeight, 5) if len(point) > 2 else round(nozzleHeight, 5)
            if p == 0:  # 路径第一点只负责空驶定位，不产生挤出。
                if enableRetraction == True:
                    openFile.write("G1 F" + str(E_FEEDRATE) + " E" + str(round(E - retractionDistance, 5)) + " ; Retraction" + "\n")
                if enableZHop == True:
                    openFile.write("G0 F" + str(G0Z_FEEDRATE) + " z" + _format_gcode_number(Z + layerHeight) + current_axis_words + "\n")
                if newChunk == True:
                    openFile.write("G0 F" + str(G0Z_FEEDRATE) + " z" + _format_gcode_number(Z + 30.0 + layerHeight) + current_axis_words + "\n")
                    newChunk = False
                if runOnce == True:  # 当前特征本层第一次写入，需要先设置 G0/G1 速度。
                    openFile.write("G0 F" + str(G0XY_FEEDRATE) + " X" + _format_gcode_number(X) + " Y" + _format_gcode_number(Y) + " z" + _format_gcode_number(Z) + current_axis_words + "\n")
                else:  # 当前特征速度已设置，只需要移动到下一条路径起点。
                    openFile.write("G0 F" + str(G0XY_FEEDRATE) + " X" + _format_gcode_number(X) + " Y" + _format_gcode_number(Y) + " z" + _format_gcode_number(Z) + current_axis_words + "\n")
                    if enableZHop == True:
                        openFile.write("G0 F" + str(G0Z_FEEDRATE) + " z" + _format_gcode_number(Z) + current_axis_words + "\n")
                    if enableRetraction == True:
                        openFile.write("G1 F" + str(E_FEEDRATE) + " E" + str(round(E, 5)) + " ; Reversed Retraction" + "\n")
            else:  # 路径第二点及后续点需要打印挤出。
                s = ((X - previousX) ** 2 + (Y - previousY) ** 2 + (Z - previousZ) ** 2) ** 0.5  # 计算当前线段三维欧氏距离。
                E += ((4.0 * layerHeight * lineWidth * s) / (np.pi * (1.75**2)))  # 根据体积守恒估算需要挤出的 1.75 mm 耗材长度。
                if runOnce == True:  # 当前特征本层第一次真正挤出，需要恢复回抽并写入打印速度。
                    if enableZHop == True:
                        openFile.write("G0 F" + str(G0Z_FEEDRATE) + " z" + _format_gcode_number(Z) + current_axis_words + "\n")
                    if enableRetraction == True:
                        openFile.write("G1 F" + str(E_FEEDRATE) + " E" + str(round(previousE, 5)) + " ; Reversed Retraction" + "\n")
                    openFile.write("G1 F" + str(PRINT_FEEDRATE) + " X" + _format_gcode_number(X) + " Y" + _format_gcode_number(Y) + " z" + _format_gcode_number(Z) + current_axis_words + " E" + _format_gcode_number(E) + "\n")
                    runOnce = False
                else:  # 速度和回抽状态已就绪，直接写入后续挤出点。
                    openFile.write("G1 F" + str(PRINT_FEEDRATE) + " X" + _format_gcode_number(X) + " Y" + _format_gcode_number(Y) + " z" + _format_gcode_number(Z) + current_axis_words + " E" + _format_gcode_number(E) + "\n")
                previousE = E

            previousX = X
            previousY = Y
            previousZ = Z

    def rotate_coordinates(coords, phi):
        """将二维坐标绕 Z 轴旋转指定角度。"""
        
        # 创建二维旋转矩阵。
        rotation_matrix = np.array([
            [np.cos(phi), -np.sin(phi)],
            [np.sin(phi), np.cos(phi)]
        ])
        
        # 确保输入坐标是 numpy 数组，便于矩阵乘法。
        coords_array = np.array(coords)
        
        # 应用旋转矩阵，得到旋转后的二维坐标。
        rotated_coords = coords_array @ rotation_matrix.T
        return rotated_coords

    def transform_paths_to_printable_orientation(layer_paths, transformation_matrices, DCM_AB):  # 同时支持 LinearRing 和 LineString。
        """
        将多层路径转换到五轴实际打印姿态。

        每层包含多个 LineString 或 LinearRing。函数先使用 Trimesh 提供的
        层变换矩阵把二维截面点转回三维，再乘以当前 A/B 联动旋转矩阵，
        得到最终可写入 G-code 的三维路径点。
        """
        
        printable_pathPoints = []
        midLayer_Z_Heights = []

        for layer_idx, (paths, transform) in enumerate(zip(layer_paths, transformation_matrices)):
            layerPaths = []
            # 逐条处理当前层路径。
            for path in paths:
                
                # 从 Shapely 路径对象中取出二维坐标。
                coords_2d = np.array(path.coords)

                # 使用该层的 to_3D 矩阵把二维坐标恢复到三维。
                coords_3d = np.array([transform_point(point, transform) for point in coords_2d])
                
                printable_coords_3d = np.array([np.matmul(DCM_AB, point3D) for point3D in coords_3d])

                layerPaths.append([(point[0], point[1], point[2]) for point in printable_coords_3d])
            printable_pathPoints.append(layerPaths)
            midLayer_Z_Heights.append(printable_coords_3d[0][2])

        return printable_pathPoints, midLayer_Z_Heights

    def transform_infill_paths_to_printable_orientation(layer_paths, transformation_matrices, DCM_AB):  # 同时支持 LinearRing 和 LineString。
        """
        将填充路径转换到五轴实际打印姿态。

        填充路径在上游结构中以 `[LineString]` 包装保存，因此这里先取出内部
        线段，再执行二维到三维转换和 A/B 联动旋转。
        """
        
        printable_pathPoints = []

        for layer_idx, (paths, transform) in enumerate(zip(layer_paths, transformation_matrices)):
            layerPaths = []
            # 逐条处理当前层填充线。
            for line in paths:
                
                # 从包装列表中取出 LineString 坐标。
                coords_2d = np.array(line[0].coords)

                # 使用该层的 to_3D 矩阵把二维填充线恢复到三维。
                coords_3d = np.array([transform_point(point, transform) for point in coords_2d])
                
                printable_coords_3d = np.array([np.matmul(DCM_AB, point3D) for point3D in coords_3d])

                layerPaths.append([(point[0], point[1], point[2]) for point in printable_coords_3d])
            printable_pathPoints.append(layerPaths)

        return printable_pathPoints



    nozzleTemp = float(printSettings[0])
    initialNozzleTemp = float(printSettings[1])
    bedTemp = float(printSettings[2])
    initialBedTemp = float(printSettings[3])
    infillPercentage = float(printSettings[4]) / 100.0
    shellThickness = int(printSettings[5])
    layerHeight = float(printSettings[6])
    lineWidth = float(layerHeight * 2.0)
    printSpeed = float(printSettings[7])
    initialPrintSpeed = float(printSettings[8])
    travelSpeed = float(printSettings[9])
    initialTravelSpeed = float(printSettings[10])
    enableZHop = bool(printSettings[11])
    enableRetraction = bool(printSettings[12])
    retractionDistance = float(printSettings[13])
    retractionSpeed = float(printSettings[14])
    enableSupports = bool(printSettings[15])
    enableBrim = bool(printSettings[16])

    # 设置进给速度。UI 使用 mm/s，G-code 需要 mm/min，因此统一乘以 60。
    E_FEEDRATE = retractionSpeed * 60.0  # 回抽轴进给速度，单位为 mm/min。
    G0XY_FEEDRATE = travelSpeed * 60.0  # XY 空驶速度，单位为 mm/min。
    G1XY_SLOW_FEEDRATE = initialPrintSpeed * 60.0  # 首层打印速度，单位为 mm/min。
    G1XY_FEEDRATE = printSpeed * 60.0  # 正常打印速度，单位为 mm/min。
    G0Z_FEEDRATE = G0XY_FEEDRATE / 5.0  # Z 轴空驶速度，当前按 XY 空驶速度的五分之一估算。

    G1XY_FEEDRATE_SHELLS = G1XY_FEEDRATE  # 外壳打印速度，当前与正常打印速度一致。
    G1XY_FEEDRATE_SOLIDINFILL = G1XY_FEEDRATE  # 实心填充打印速度，当前与正常打印速度一致。
    G1XY_FEEDRATE_INTERNALINFILL = G1XY_FEEDRATE  # 内部填充打印速度，当前与正常打印速度一致。
    linkedAxis = _linked_axis_config(printSettings)

    directions = np.array(directions)
    directions[:, 1] = 90 - directions[:, 1]
    directions[0] = [0.0, 0.0]
    AMOVE_Degrees = [sublist[1] for sublist in directions]
    AMOVE_Degrees.append(0.0)
    BMOVE_Degrees = [sublist[0] for sublist in directions]
    BMOVE_Degrees.append(0.0)

    openFile = open(newFile, "w")

    """写出 G-code 文件头。"""
    openFile.write(";" + "SLICER:       Fractal Cortex" + "\n")
    openFile.write(";" + "FIRMWARE:     Klipper" + "\n")
    openFile.write(";" + "FILE:         " + savedFileName + "\n")
    openFile.write(";" + "--------------------------" + "\n")
    openFile.write(";" + "PRINT SETTINGS:" + "\n")
    openFile.write(";" + "--------------------------" + "\n")
    openFile.write(";" + "initialNozzleTemp:   " + str(initialNozzleTemp) + "\n")
    openFile.write(";" + "nozzleTemp:          " + str(nozzleTemp) + "\n")
    openFile.write(";" + "initialBedTemp:      " + str(initialBedTemp) + "\n")
    openFile.write(";" + "bedTemp:             " + str(bedTemp) + "\n")
    openFile.write(";" + "infillPercentage:    " + str(infillPercentage) + "\n")
    openFile.write(";" + "shellThickness:      " + str(shellThickness) + "\n")
    openFile.write(";" + "layerHeight:         " + str(layerHeight) + "\n")
    openFile.write(";" + "lineWidth:           " + str(lineWidth) + "\n")
    openFile.write(";" + "initialPrintSpeed:   " + str(initialPrintSpeed) + "\n")
    openFile.write(";" + "printSpeed:          " + str(printSpeed) + "\n")
    openFile.write(";" + "initialTravelSpeed:  " + str(initialTravelSpeed) + "\n")
    openFile.write(";" + "travelSpeed:         " + str(travelSpeed) + "\n")
    openFile.write(";" + "enableZHop:          " + str(enableZHop) + "\n")
    openFile.write(";" + "enableRetraction:    " + str(enableRetraction) + "\n")
    if enableRetraction == True:
        openFile.write(";" + "retractionDistance:  " + str(retractionDistance) + "\n")
        openFile.write(";" + "retractionSpeed:     " + str(retractionSpeed) + "\n")
    openFile.write(";" + "enableSupports:      " + str(enableSupports) + "\n")
    openFile.write(";" + "enableBrim:          " + str(enableBrim) + "\n")
    openFile.write(";" + "linkedAxis1Symbol:   " + linkedAxis["axisA"] + "\n")
    openFile.write(";" + "linkedAxis2Symbol:   " + linkedAxis["axisB"] + "\n")
    openFile.write(";" + "fiveAxisOutput:      Inline XYZ" + linkedAxis["axisA"] + linkedAxis["axisB"] + " motion words" + "\n")
    openFile.write(";" + "--------------------------" + "\n")
    openFile.write("G28                   ;Home printer axes" + "\n")
    openFile.write("M140 S" + str(initialBedTemp) + "            ;Set initial bed temp" + "\n")
    openFile.write("M105                  ;Get nozzle temp" + "\n")
    openFile.write("M190 S" + str(initialBedTemp) + "            ;Set initial bed temperature and wait" + "\n")
    openFile.write("M104 S" + str(initialNozzleTemp) + "           ;Set initial nozzle temperature" + "\n")
    openFile.write("M105                  ;Get nozzle temp" + "\n")
    openFile.write("M109 S" + str(initialNozzleTemp) + "           ;Set initial nozzle temperature and wait" + "\n")
    openFile.write("M82                   ;Absolute extrusion mode" + "\n")
    openFile.write("Z_TILT_ADJUST         ;Z Tilt the Bed" + "\n")
    openFile.write("G0 F3000.0 Z30.0" + "\n")
    openFile.write("G0 X0.0 Y0.0" + "\n")
    openFile.write("DIAG_CENTRALIZE" + "\n")
    openFile.write("G0 X0.0 Y0.0" + "\n")
    openFile.write("G92 E0                ;Reset extruder position" + "\n")
    openFile.write("G1 F2700 E-5" + "\n")
    openFile.write(";END OF HEADER" + "\n")

    # 后续可以在打印开始前增加一段靠近热床外径的清料线，用于旋转热床时给喷嘴留出安全空间。

    """写出 G-code 主体。"""
    numChunks = len(chunk_transform3DList)

    global E, previousE
    E = 0  # 累计挤出长度，按 1.75 mm 直径耗材计算。
    previousE = 0
    nozzleHeight = 0.0
    current_axis_words = _linked_axis_words(linkedAxis, 0.0, 0.0)

    for key in chunk_transform3DList: # 按 chunk 顺序写出五轴路径。
        chunkIndex = int(key)
        current_axis_words = _linked_axis_words(
            linkedAxis,
            AMOVE_Degrees[chunkIndex],
            BMOVE_Degrees[chunkIndex],
        )
        openFile.write(";" + "Chunk " + key + "\n")
        transform3DList = chunk_transform3DList[key]
        shellRingsListList = chunk_shellRingsListList[key]
        optimizedSolidInfills = chunk_optimizedSolidInfills[key]
        optimizedInternalInfills = chunk_optimizedInternalInfills[key]

        theta = BMOVE_Degrees[chunkIndex]*(np.pi/180.0)
        phi = AMOVE_Degrees[chunkIndex]*(np.pi/180.0)
        DCM_AB = np.eye(3) 

        if key != '0': # 非初始 chunk 需要先移动到安全位置，再切换联动旋转轴角度。
            newChunk = True
            previous_axis_words = _linked_axis_words(
                linkedAxis,
                AMOVE_Degrees[chunkIndex - 1],
                BMOVE_Degrees[chunkIndex - 1],
            )
            clearHeight = nozzleHeight + 10.0
            openFile.write("G0 F" + str(G0Z_FEEDRATE) + " z" + _format_gcode_number(clearHeight) + previous_axis_words + "; Moving z axis to clear " + linkedAxis["axisPair"] + " motion" + "\n")
            openFile.write("G0 F" + str(G0XY_FEEDRATE) + " X0 Y-175 z" + _format_gcode_number(clearHeight) + previous_axis_words + "; Moving print head to clear " + linkedAxis["axisPair"] + " motion" + "\n")
            openFile.write("G0 F" + str(G0Z_FEEDRATE) + " X0 Y-175 z" + _format_gcode_number(clearHeight) + current_axis_words + "\n")
            openFile.write("; " + linkedAxis["axisPair"] + " Axis Motion Complete" + "\n")
            
            QA = np.array([[np.cos(phi), -np.sin(phi), 0], [np.sin(phi), np.cos(phi), 0], [0, 0, 1]])
            QB = np.array([[1, 0, 0], [0, np.cos(theta), -np.sin(theta)], [0, np.sin(theta), np.cos(theta)]])
            DCM_AB = np.matmul(QB, QA)
        elif key == '0':
            newChunk = False

        printable_shell_pathPoints, midLayer_Z_Heights = transform_paths_to_printable_orientation(shellRingsListList, transform3DList, DCM_AB)
        printable_solidInfill_pathPoints = transform_infill_paths_to_printable_orientation(optimizedSolidInfills, transform3DList, DCM_AB)
        printable_internalInfill_pathPoints = transform_infill_paths_to_printable_orientation(optimizedInternalInfills, transform3DList, DCM_AB)

        numLayers = len(transform3DList)
        for k in range(numLayers):  # 逐层写出当前 chunk 的路径。
            openFile.write(";" + "Layer " + str(k) + "\n")
            if k == 0:  # 首层使用首层速度，提升附着稳定性。
                G0XY_FEEDRATE = initialTravelSpeed * 60.0
                G1XY_FEEDRATE_SHELLS = G1XY_SLOW_FEEDRATE
                G1XY_FEEDRATE_SOLIDINFILL = G1XY_SLOW_FEEDRATE
                G1XY_FEEDRATE_INTERNALINFILL = G1XY_SLOW_FEEDRATE
            else:  # 非首层使用正常速度。
                G0XY_FEEDRATE = travelSpeed * 60.0
                G1XY_FEEDRATE_SHELLS = G1XY_FEEDRATE
                G1XY_FEEDRATE_SOLIDINFILL = G1XY_FEEDRATE
                G1XY_FEEDRATE_INTERNALINFILL = G1XY_FEEDRATE
            if k == 1:  # 从第二层开始切换到正常喷嘴和热床温度。
                openFile.write("M104 S" + str(nozzleTemp) + "   ;Set nozzle temperature for remainder of print" + "\n")
                openFile.write("M140 S" + str(bedTemp) + "    ;Set bed temp for remainder of print" + "\n")

            current3DTransform = transform3DList[k]

            if current3DTransform.shape == (4, 4):  # 只有存在有效层变换矩阵时才写出该层；空层说明模型在该高度没有截面。
                nozzleHeight = midLayer_Z_Heights[k] + 0.5 * layerHeight # 喷嘴中心高度等于层中面高度加半个层高。

                """写出当前层 Z 定位命令。"""
                openFile.write("G0 F" + str(G0Z_FEEDRATE) + " z" + _format_gcode_number(nozzleHeight) + current_axis_words + "\n")

                if key == '0' and k == 0 and adhesionList[0] != []: # 只在初始 chunk 的首层写出边裙。
                    """写出附着路径标题。"""
                    if enableBrim == True:
                        openFile.write(";" + "Brim" + "\n")

                    flattened_adhesion_rings = sum(adhesionList[0], [])
                    flattened_adhesion_rings.reverse() # 反转边裙顺序，先打印外圈，再逐步靠近模型外壳。

                    adhesions = [list(ring.coords) for ring in flattened_adhesion_rings]
                    
                    runOnce = True  # 表示本层当前特征刚开始，第一次路径需要写入速度和状态恢复命令。
                    newChunk = False
                    for a in adhesions:  # 同一层多条边裙路径之间用 G0 空驶衔接。
                        pathPoints = a
                        """写出 X/Y/Z/E 运动命令。"""
                        transcribe_pathPoints_to_gcode(pathPoints, G1XY_FEEDRATE_SHELLS, runOnce, newChunk)
                        runOnce = False
                
                if shellRingsListList[k] != []:  # 该层存在外壳路径时写出外壳 G-code。
                    """写出外壳特征标题。"""
                    openFile.write(";" + "Shell(s)" + "\n")

                    shells = printable_shell_pathPoints[k]

                    runOnce = True  # 每个特征块开始时都需要重新处理初始空驶和回抽恢复。
                    for shell in shells:  # 同一层多条外壳路径之间用 G0 空驶衔接。
                        pathPoints = shell
                        
                        """写出 X/Y/Z/E 运动命令。"""
                        transcribe_pathPoints_to_gcode(pathPoints, G1XY_FEEDRATE_SHELLS, runOnce, newChunk)
                        runOnce = False
                        newChunk = False

                if optimizedSolidInfills[k] != []:  # 该层存在实心填充路径时写出实心填充 G-code。
                    """写出实心填充特征标题。"""
                    openFile.write(";" + "Solid Infill" + "\n")

                    solidInfills = printable_solidInfill_pathPoints[k]

                    runOnce = True
                    for solidInfill in solidInfills:
                        pathPoints = solidInfill

                        """写出 X/Y/Z/E 运动命令。"""
                        transcribe_pathPoints_to_gcode(pathPoints, G1XY_FEEDRATE_SOLIDINFILL, runOnce, newChunk)
                        runOnce = False
                        newChunk = False

                if optimizedInternalInfills[k] != []:  # 该层存在内部稀疏填充路径时写出内部填充 G-code。
                    """写出内部填充特征标题。"""
                    openFile.write(";" + "Internal Infill" + "\n")

                    internalInfills = printable_internalInfill_pathPoints[k]

                    runOnce = True
                    for internalInfill in internalInfills:
                        pathPoints = internalInfill

                        """写出 X/Y/Z/E 运动命令。"""
                        transcribe_pathPoints_to_gcode(pathPoints, G1XY_FEEDRATE_INTERNALINFILL, runOnce, newChunk)
                        runOnce = False
                        newChunk = False



    """写出 G-code 文件尾。"""
    openFile.write(";" + "FOOTER:" + "\n")
    openFile.write("G1 F" + str(E_FEEDRATE) + " E" + str(round(E - 2.0, 5)) + " ; Retract for end of print" + "\n") #######
    openFile.write("G0 F" + str(G0Z_FEEDRATE) + " z" + _format_gcode_number(nozzleHeight + layerHeight) + current_axis_words + "\n")
    openFile.write("M140 S0       ;Set bed temp to zero" + "\n")
    openFile.write("M104 S0       ;Set nozzle temp to zero" + "\n")
    openFile.write("G28 Y         ;Home X-Axis" + "\n")
    openFile.write("G28 X         ;Home X-Axis" + "\n")
    openFile.write("G0 F" + str(G0Z_FEEDRATE) + " z" + _format_gcode_number(nozzleHeight + layerHeight) + _linked_axis_words(linkedAxis, 0.0, 0.0) + "\n")
    openFile.write(";" + linkedAxis["axisPair"] + " Axes Returned To Zero" + "\n")
    openFile.write(";" + "End of GCODE" + "\n")

    openFile.close()


def write_3_axis_gcode(newFile, savedFileName, printSettings, transform3DList, adhesionList, shellRingsListList, optimizedInternalInfills, optimizedSolidInfills):
    """把三轴切片结果写出为 G-code 文件。

    输入列表由 `slice_in_3_axes()` 生成，并按层号一一对应。写出顺序为：
    文件头命令、每层特征块、挤出移动、可选回抽和 Z hop 移动，最后写入
    关机和归零相关尾部命令。
    """
    
    def transcribe_pathPoints_to_gcode(pathPoints, PRINT_FEEDRATE, runOnce):
        """把一条三轴可打印路径写成空驶和挤出移动。"""
        global E, previousE

        for p in range(len(pathPoints)):
            point = pathPoints[p]
            X = round(point[0], 5)
            Y = round(point[1], 5)
            if p == 0:  # 路径第一点只负责空驶定位，不产生挤出。
                if enableRetraction == True:
                    openFile.write("G1 F" + str(E_FEEDRATE) + " E" + str(round(E - retractionDistance, 5)) + " ; Retraction" + "\n")
                if enableZHop == True:
                    openFile.write("G0 F" + str(G0Z_FEEDRATE) + " Z" + str(round(nozzleHeight + layerHeight, 5)) + "\n")                    
                if runOnce == True:  # 当前特征本层第一次写入，需要先设置 G0/G1 速度。
                    openFile.write("G0 F" + str(G0XY_FEEDRATE) + " X" + str(X) + " Y" + str(Y) + "\n")
                else:  # 当前特征速度已设置，只需要移动到下一条路径起点。
                    openFile.write("G0 F" + str(G0XY_FEEDRATE) + " X" + str(X) + " Y" + str(Y) + "\n") # 写出纯 XY 空驶移动。
                    if enableZHop == True:
                        openFile.write("G0 F" + str(G0Z_FEEDRATE) + " Z" + str(round(nozzleHeight, 5)) + "\n")
                    if enableRetraction == True:
                        openFile.write("G1 F" + str(E_FEEDRATE) + " E" + str(round(E, 5)) + " ; Reversed Retraction" + "\n")
            else:  # 路径第二点及后续点需要打印挤出。
                s = ((X - previousX) ** 2 + (Y - previousY) ** 2) ** 0.5  # 计算当前 XY 线段长度。
                E += ((4.0 * layerHeight * lineWidth * s) / (np.pi * (1.75**2)))  # 根据体积守恒估算需要挤出的 1.75 mm 耗材长度。
                if runOnce == True:  # 当前特征本层第一次真正挤出，需要恢复回抽并写入打印速度。
                    if enableZHop == True:
                        openFile.write("G0 F" + str(G0Z_FEEDRATE) + " Z"+ str(round(nozzleHeight, 5)) + "\n")
                    if enableRetraction == True:
                        openFile.write("G1 F" + str(E_FEEDRATE) + " E" + str(round(previousE, 5)) + " ; Reversed Retraction" + "\n")
                    openFile.write("G1 F" + str(PRINT_FEEDRATE) + " X" + str(X) + " Y"+ str(Y) + " E" + str(round(E, 5)) + "\n")
                    runOnce = False
                else:  # 速度和回抽状态已就绪，直接写入后续挤出点。
                    openFile.write("G1 F" + str(PRINT_FEEDRATE) + " X" + str(X) + " Y"+ str(Y) + " E" + str(round(E, 5)) + "\n") # 写出普通 XY 挤出移动。
                previousE = E

            previousX = X
            previousY = Y

    nozzleTemp = float(printSettings[0])
    initialNozzleTemp = float(printSettings[1])
    bedTemp = float(printSettings[2])
    initialBedTemp = float(printSettings[3])
    infillPercentage = float(printSettings[4]) / 100.0
    shellThickness = int(printSettings[5])
    layerHeight = float(printSettings[6])
    lineWidth = float(layerHeight * 2.0)
    printSpeed = float(printSettings[7])
    initialPrintSpeed = float(printSettings[8])
    travelSpeed = float(printSettings[9])
    initialTravelSpeed = float(printSettings[10])
    enableZHop = bool(printSettings[11])
    enableRetraction = bool(printSettings[12])
    retractionDistance = float(printSettings[13])
    retractionSpeed = float(printSettings[14])
    enableSupports = bool(printSettings[15])
    enableBrim = bool(printSettings[16])

    # 设置进给速度。UI 使用 mm/s，G-code 需要 mm/min，因此统一乘以 60。
    E_FEEDRATE = retractionSpeed * 60.0  # 回抽轴进给速度，单位为 mm/min。
    G0XY_FEEDRATE = travelSpeed * 60.0  # XY 空驶速度，单位为 mm/min。
    G1XY_SLOW_FEEDRATE = initialPrintSpeed * 60.0  # 首层打印速度，单位为 mm/min。
    G1XY_FEEDRATE = printSpeed * 60.0  # 正常打印速度，单位为 mm/min。
    G0Z_FEEDRATE = G0XY_FEEDRATE / 5.0  # Z 轴空驶速度，当前按 XY 空驶速度的五分之一估算。

    G1XY_FEEDRATE_SHELLS = G1XY_FEEDRATE  # 外壳打印速度，当前与正常打印速度一致。
    G1XY_FEEDRATE_SOLIDINFILL = G1XY_FEEDRATE  # 实心填充打印速度，当前与正常打印速度一致。
    G1XY_FEEDRATE_INTERNALINFILL = G1XY_FEEDRATE  # 内部填充打印速度，当前与正常打印速度一致。

    openFile = open(newFile, "w")

    """写出 G-code 文件头。"""
    openFile.write(";" + "SLICER:       Fractal Cortex" + "\n")
    openFile.write(";" + "FIRMWARE:     Klipper" + "\n")
    openFile.write(";" + "FILE:         " + savedFileName + "\n")
    openFile.write(";" + "--------------------------" + "\n")
    openFile.write(";" + "PRINT SETTINGS:" + "\n")
    openFile.write(";" + "--------------------------" + "\n")
    openFile.write(";" + "initialNozzleTemp:   " + str(initialNozzleTemp) + "\n")
    openFile.write(";" + "nozzleTemp:          " + str(nozzleTemp) + "\n")
    openFile.write(";" + "initialBedTemp:      " + str(initialBedTemp) + "\n")
    openFile.write(";" + "bedTemp:             " + str(bedTemp) + "\n")
    openFile.write(";" + "infillPercentage:    " + str(infillPercentage) + "\n")
    openFile.write(";" + "shellThickness:      " + str(shellThickness) + "\n")
    openFile.write(";" + "layerHeight:         " + str(layerHeight) + "\n")
    openFile.write(";" + "lineWidth:           " + str(lineWidth) + "\n")
    openFile.write(";" + "initialPrintSpeed:   " + str(initialPrintSpeed) + "\n")
    openFile.write(";" + "printSpeed:          " + str(printSpeed) + "\n")
    openFile.write(";" + "initialTravelSpeed:  " + str(initialTravelSpeed) + "\n")
    openFile.write(";" + "travelSpeed:         " + str(travelSpeed) + "\n")
    openFile.write(";" + "enableZHop:          " + str(enableZHop) + "\n")
    openFile.write(";" + "enableRetraction:    " + str(enableRetraction) + "\n")
    if enableRetraction == True:
        openFile.write(";" + "retractionDistance:  " + str(retractionDistance) + "\n")
        openFile.write(";" + "retractionSpeed:     " + str(retractionSpeed) + "\n")
    openFile.write(";" + "enableSupports:      " + str(enableSupports) + "\n")
    openFile.write(";" + "enableBrim:          " + str(enableBrim) + "\n")
    openFile.write(";" + "--------------------------" + "\n")
    openFile.write("G28                   ;Home X, Y, & Z axes" + "\n")
    openFile.write("M140 S" + str(initialBedTemp) + "            ;Set initial bed temp" + "\n")
    openFile.write("M105                  ;Get nozzle temp" + "\n")
    openFile.write("M190 S" + str(initialBedTemp) + "            ;Set initial bed temperature and wait" + "\n")
    openFile.write("M104 S" + str(initialNozzleTemp) + "           ;Set initial nozzle temperature" + "\n")
    openFile.write("M105                  ;Get nozzle temp" + "\n")
    openFile.write("M109 S" + str(initialNozzleTemp) + "           ;Set initial nozzle temperature and wait" + "\n")
    openFile.write("M82                   ;Absolute extrusion mode" + "\n")
    openFile.write("Z_TILT_ADJUST         ;Z Tilt the Bed" + "\n")
    openFile.write("G28 Y                 ;Home Y Axis" + "\n")
    openFile.write("G0 F3000.0 Z30.0" + "\n")
    openFile.write("G0 X0.0 Y0.0" + "\n")
    openFile.write("G92 E0                ;Reset extruder position" + "\n")
    openFile.write("G1 F2700 E-5" + "\n")
    openFile.write(";END OF HEADER" + "\n")

    # 后续可以在打印开始前增加一段靠近热床外径的清料线，用于旋转热床时给喷嘴留出安全空间。

    """写出 G-code 主体。"""
    # 写 Z 命令时要加半个层高，使喷嘴位于当前层中心高度。
    numLayers = len(transform3DList)
    print(numLayers)

    global E, previousE
    E = 0  # 累计挤出长度，按 1.75 mm 直径耗材计算。
    previousE = 0
    for k in range(numLayers):  # 逐层写出三轴路径。
        openFile.write(";" + "Layer " + str(k) + "\n")
        if k == 0:  # 首层使用首层速度，提升附着稳定性。
            G0XY_FEEDRATE = initialTravelSpeed * 60.0
            G1XY_FEEDRATE_SHELLS = G1XY_SLOW_FEEDRATE
            G1XY_FEEDRATE_SOLIDINFILL = G1XY_SLOW_FEEDRATE
            G1XY_FEEDRATE_INTERNALINFILL = G1XY_SLOW_FEEDRATE
        else:  # 非首层使用正常速度。
            G0XY_FEEDRATE = travelSpeed * 60.0
            G1XY_FEEDRATE_SHELLS = G1XY_FEEDRATE
            G1XY_FEEDRATE_SOLIDINFILL = G1XY_FEEDRATE
            G1XY_FEEDRATE_INTERNALINFILL = G1XY_FEEDRATE
        if k == 1:  # 从第二层开始切换到正常喷嘴和热床温度。
            openFile.write("M104 S" + str(nozzleTemp) + "   ;Set nozzle temperature for remainder of print" + "\n")
            openFile.write("M140 S" + str(bedTemp) + "    ;Set bed temp for remainder of print" + "\n")

        current3DTransform = transform3DList[k]

        if current3DTransform.shape == (4, 4):  # 只有存在有效层变换矩阵时才写出该层；空层说明模型在该高度没有截面。
            nozzleHeight = current3DTransform[2][3] + 0.5 * layerHeight  # 喷嘴中心高度等于截面高度加半个层高。

            """写出当前层 Z 定位命令。"""
            openFile.write("G0 F" + str(G0Z_FEEDRATE) + " Z" + str(round(nozzleHeight, 5)) + "\n")

            if k == 0 and adhesionList[0] != []: # 只在首层写出边裙。
                """写出附着路径标题。"""
                if enableBrim == True:
                    openFile.write(";" + "Brim" + "\n")

                flattened_adhesion_rings = sum(adhesionList[0], [])
                flattened_adhesion_rings.reverse() # 反转边裙顺序，先打印外圈，再逐步靠近模型外壳。

                adhesions = [list(ring.coords) for ring in flattened_adhesion_rings]
                
                runOnce = True  # 表示本层当前特征刚开始，第一次路径需要写入速度和状态恢复命令。
                for a in adhesions:  # 同一层多条边裙路径之间用 G0 空驶衔接。
                    pathPoints = a
                    """写出 X/Y/E 运动命令。"""
                    transcribe_pathPoints_to_gcode(pathPoints, G1XY_FEEDRATE_SHELLS, runOnce)
                    runOnce = False
            
            if shellRingsListList[k] != []:  # 该层存在外壳路径时写出外壳 G-code。
                """写出外壳特征标题。"""
                openFile.write(";" + "Shell(s)" + "\n")

                shells = [list(ring.coords) for ring in shellRingsListList[k]]

                runOnce = True  # 每个特征块开始时都需要重新处理初始空驶和回抽恢复。
                for shell in shells:  # 同一层多条外壳路径之间用 G0 空驶衔接。
                    pathPoints = shell
                    """写出 X/Y/E 运动命令。"""
                    transcribe_pathPoints_to_gcode(pathPoints, G1XY_FEEDRATE_SHELLS, runOnce)
                    runOnce = False

            if optimizedSolidInfills[k] != []:  # 该层存在实心填充路径时写出实心填充 G-code。
                """写出实心填充特征标题。"""
                openFile.write(";" + "Solid Infill" + "\n")

                solidInfills = [list(line[0].coords) for line in optimizedSolidInfills[k]]

                runOnce = True
                for solidInfill in solidInfills:
                    pathPoints = solidInfill
                    """写出 X/Y/E 运动命令。"""
                    transcribe_pathPoints_to_gcode(pathPoints, G1XY_FEEDRATE_SOLIDINFILL, runOnce)
                    runOnce = False

            if optimizedInternalInfills[k] != []:  # 该层存在内部稀疏填充路径时写出内部填充 G-code。
                """写出内部填充特征标题。"""
                openFile.write(";" + "Internal Infill" + "\n")

                internalInfills = [list(line[0].coords) for line in optimizedInternalInfills[k]]

                runOnce = True
                for internalInfill in internalInfills:
                    pathPoints = internalInfill
                    """写出 X/Y/E 运动命令。"""
                    transcribe_pathPoints_to_gcode(pathPoints, G1XY_FEEDRATE_INTERNALINFILL, runOnce)
                    runOnce = False

    """写出 G-code 文件尾。"""
    openFile.write(";" + "FOOTER:" + "\n")
    openFile.write("G1 F" + str(E_FEEDRATE) + " E" + str(round(E - 2.0, 5)) + " ; Retract for end of print" + "\n")
    openFile.write("G0 F" + str(G0Z_FEEDRATE) + " Z" + str(round(nozzleHeight + layerHeight, 5)) + "\n")
    openFile.write("M140 S0       ;Set bed temp to zero" + "\n")
    openFile.write("M104 S0       ;Set nozzle temp to zero" + "\n")
    openFile.write("G28 Y         ;Home X-Axis" + "\n")
    openFile.write("G28 X         ;Home X-Axis" + "\n")
    openFile.write(";" + "End of GCODE" + "\n")

    openFile.close()


def transform_point(point, matrix):
    """使用 4x4 变换矩阵把二维点转换为三维点。"""
    
    # 将二维点扩展成齐次坐标，Z 固定为 0。
    point_h = np.array([point[0], point[1], 0, 1])
    # 应用二维截面到三维空间的变换。
    transformed = matrix @ point_h
    # 只返回 X、Y、Z 三个坐标。
    return transformed[:3]


def paths_to_3d_segments(layer_paths, transformation_matrices):  # 同时支持 LinearRing 和 LineString。
    """
    把多层二维路径转换成三维线段数组。

    每层包含多个 LineString 或 LinearRing。函数会对每层应用对应的 to_3D
    变换矩阵，并把相邻点连接成线段，供 OpenGL 预览一次性绘制。
    """
    
    all_segments = []

    for layer_idx, (paths, transform) in enumerate(zip(layer_paths, transformation_matrices)):
        # 逐条处理当前层路径。
        for path in paths:
            
            # 从 Shapely 路径对象中取出二维坐标。
            coords_2d = np.array(path.coords)

            # 把二维点逐个映射到三维空间。
            coords_3d = np.array([transform_point(point, transform) for point in coords_2d])

            # 根据转换后的点创建线段。
            # LineString 使用所有相邻点形成线段。
            # LinearRing 的最后一点与第一点重复，线段创建时自然连接到闭合点。
            segments = np.zeros((len(coords_3d) - 1, 6))
            segments[:, :3] = coords_3d[:-1]  # 每行前三列保存线段起点。
            segments[:, 3:] = coords_3d[1:]  # 每行后三列保存线段终点。

            all_segments.append(segments)

    # 把所有层、所有路径的线段合并成一个数组，便于渲染层直接上传。
    if all_segments:
        return np.vstack(all_segments)
    else:
        return np.zeros((0, 6))


def convert_slice_data_to_renderable_vertices(transform3DList, adhesionList, shellRingsListList, optimizedInternalInfills, optimizedSolidInfills):
    print("Starting timer for plotting preparation (PARALLEL)")
    start = time.time()

    if isinstance(transform3DList, dict): # 五轴模式会传入按 chunk 存储的字典，这里摊平成普通层列表。
        transform3DList = [num for sublist in transform3DList.values() for num in sublist]
        shellRingsListList = [num for sublist in shellRingsListList.values() for num in sublist]
        optimizedInternalInfills = [num for sublist in optimizedInternalInfills.values() for num in sublist]
        optimizedSolidInfills = [num for sublist in optimizedSolidInfills.values() for num in sublist]

    adhesionPath3D = paths_to_3d_segments(adhesionList[0], [transform3DList[0]]*len(transform3DList))
    
    shellPath3D = paths_to_3d_segments(shellRingsListList, transform3DList)
    
    solidInfillPath3D = paths_to_3d_segments([[ls[0] for ls in layer] for layer in optimizedSolidInfills], transform3DList)

    internalInfillPath3D = paths_to_3d_segments([[ls[0] for ls in layer] for layer in optimizedInternalInfills], transform3DList)

    del transform3DList, adhesionList, shellRingsListList, optimizedInternalInfills, optimizedSolidInfills

    adhesionPathsCombined = adhesionPath3D
    shellPathsCombined = shellPath3D
    internalInfillPathsCombined = internalInfillPath3D
    solidInfillPathsCombined = solidInfillPath3D

    end = time.time() - start
    print("Plotting preparation took ", end, "seconds.", "\n")

    return adhesionPathsCombined, shellPathsCombined, internalInfillPathsCombined, solidInfillPathsCombined


# 为并行切片任务设置相对保守的进程数量。
try:
    maxProcesses = os.cpu_count()       # 读取当前机器可用 CPU 核心数。
    workerBees = int(maxProcesses / 2)  # 默认只使用一半核心，给界面和系统其它任务保留余量。
except:
    workerBees = 2                      # 读取核心数失败时使用 2 个进程作为保守默认值。
