//@version=5
indicator("高级K线组合策略 V12 - 修复版", overlay=true, max_lines_count=500, max_labels_count=100)

// ============ 参数设置 ============
ma_length = input.int(60, "MA周期", minval=1, maxval=200)
ma_color = #FF0000
bb_length = input.int(20, "布林线周期", minval=1, maxval=100)
bb_mult = input.float(2.0, "布林线标准差倍数", minval=0.5, maxval=5.0)
bb_color = #FFFF00
doji_body_ratio = input.float(0.1, "十字星实体比例", minval=0.01, maxval=0.3, step=0.01)
strong_body_ratio = input.float(0.7, "强K线实体比例", minval=0.5, maxval=0.9, step=0.1)
parallel_threshold = input.float(1.5, "平行K线阈值", minval=1.0, maxval=3.0, step=0.1)
clean_after_bars = input.int(1000, "划线清理周期", minval=100, maxval=5000)
remove_on_break = input.bool(true, "突破后移除划线")

// ===== 画线样式参数 =====
line_width = input.int(2, "信号画线粗细", options=[1,2,3,4], group="画线样式")
line_color_custom = input.color(#FFFFFF, "信号画线颜色", group="画线样式")

// ============ 全局变量 ============
var int history_size = 500
var used_bar_indices = array.new_int(0)
var signal_lines = array.new_line(0)
var signal_start_bars = array.new_int(0)
var signal_prices = array.new_float(0)
var signal_types = array.new_string(0)
var signal_lengths = array.new_int(0)
var int last_clean_bar = 0

// 用于信号统计的简化方法
var int yin_to_yang_count = 0
var int yang_to_yin_count = 0
var int huanhun_count = 0
var int limin_count = 0
var int pattern1_count = 0
var int pattern2_count = 0

// ============ 核心辅助函数 ============
new_color(color hex_color, int alpha) =>
    color.new(hex_color, alpha)

is_bar_used(int offset) =>
    offset < 0 or offset >= history_size ? false : array.includes(used_bar_indices, bar_index - offset)

mark_bars_used(int start_offset, int length) =>
    for i = 0 to length - 1
        offset = start_offset + i
        if offset >= 0 and offset < history_size
            target_bar = bar_index - offset
            if not array.includes(used_bar_indices, target_bar)
                array.push(used_bar_indices, target_bar)
                if array.size(used_bar_indices) > history_size
                    array.shift(used_bar_indices)

// ============ 计算指标 ============
ma60 = ta.sma(close, ma_length)
plot(ma60, "MA60", ma_color, 2)

bb_basis = ta.sma(close, bb_length)
bb_dev = bb_mult * ta.stdev(close, bb_length)
bb_upper = bb_basis + bb_dev
bb_lower = bb_basis - bb_dev

plot(bb_basis, "布林中轨", bb_color, 1)
p1 = plot(bb_upper, "布林上轨", bb_color, 1, display=display.all - display.status_line)
p2 = plot(bb_lower, "布林下轨", bb_color, 1, display=display.all - display.status_line)
fill(p1, p2, color=new_color(bb_color, 90), title="布林带填充")

// ============ 基础K线定义 ============
entity_length = math.abs(close - open)
yang_line = close > open
yin_line = close < open

// ============ 信号管理函数 ============
clean_old_signals() =>
    if array.size(signal_lines) > 0
        i = 0
        while i < array.size(signal_lines)
            should_remove = false
            start_bar = array.get(signal_start_bars, i)
            signal_price = array.get(signal_prices, i)
            signal_type = array.get(signal_types, i)
            signal_length = array.get(signal_lengths, i)
            
            // 计算信号生成后新出现的K线数量：排除组合自身的K线
            bars_after_signal = bar_index - (start_bar + signal_length)
            
            // 条件1：超过清理周期自动移除
            if bars_after_signal > clean_after_bars
                should_remove := true
            
            // 条件2：价格突破信号线（仅判断信号生成后的新K线，排除组合最后一根K线）
            if remove_on_break and bars_after_signal > 0 and not should_remove
                // 支撑类信号：后续新K线的最低价跌破信号线
                if signal_type == "yin_to_yang" or signal_type == "limin" or signal_type == "pattern1"
                    if ta.lowest(low, bars_after_signal) < signal_price
                        should_remove := true
                // 压力类信号：后续新K线的最高价突破信号线
                if signal_type == "yang_to_yin" or signal_type == "huanhun" or signal_type == "pattern2"
                    if ta.highest(high, bars_after_signal) > signal_price
                        should_remove := true
            
            if should_remove
                line.delete(array.get(signal_lines, i))
                array.remove(signal_lines, i)
                array.remove(signal_start_bars, i)
                array.remove(signal_prices, i)
                array.remove(signal_types, i)
                array.remove(signal_lengths, i)
            else
                i := i + 1

add_signal(string type_str, string label_text, int start_offset, int pattern_length) =>
    bars_available = true
    for i = 0 to pattern_length - 1
        if is_bar_used(start_offset + i)
            bars_available := false
            break
    
    if bars_available
        // 计算价格水平 - 使用组合最后一根K线（当前K线）的收盘价
        price_level = close
        
        // 计算画线的起点和终点
        start_bar = bar_index - pattern_length + 1
        end_bar = bar_index
        
        // 确定标签颜色
        label_color = type_str == "yin_to_yang" or type_str == "limin" or type_str == "pattern1" ? 
                     color.green : color.red
        
        // 生成信号线
        line_id = line.new(x1=start_bar, y1=price_level,x2=end_bar, y2=price_level,color=line_color_custom, width=line_width, style=line.style_solid,extend=extend.both)
        
        // 添加标签
        label.new(x=end_bar, y=price_level, text=label_text, color=label_color, textcolor=color.white,style=label.style_label_center,size=size.small)
        
        // 更新信号计数
        switch type_str
            "yin_to_yang" => yin_to_yang_count += 1
            "yang_to_yin" => yang_to_yin_count += 1
            "huanhun" => huanhun_count += 1
            "limin" => limin_count += 1
            "pattern1" => pattern1_count += 1
            "pattern2" => pattern2_count += 1
        
        // 存储信号信息
        array.push(signal_lines, line_id)
        array.push(signal_start_bars, start_bar)
        array.push(signal_prices, price_level)
        array.push(signal_types, type_str)
        array.push(signal_lengths, pattern_length)
        
        // 标记已使用的bar
        mark_bars_used(start_offset, pattern_length)
        
        true
    else
        false

// ============ K线组合检测 ============
check_yin_to_yang() =>
    not is_bar_used(1) and not is_bar_used(0) and yin_line[1] and yang_line[0] ? add_signal("yin_to_yang", "阴转阳", 1, 2) : false

check_yang_to_yin() =>
    not is_bar_used(1) and not is_bar_used(0) and yang_line[1] and yin_line[0] ? add_signal("yang_to_yin", "阳转阴", 1, 2) : false

check_huanhun() =>
    not is_bar_used(2) and not is_bar_used(1) and not is_bar_used(0) and yang_line[2] and yin_line[1] and yang_line[0] ? add_signal("huanhun", "黄昏之星", 2, 3) : false

check_limin() =>
    not is_bar_used(2) and not is_bar_used(1) and not is_bar_used(0) and yin_line[2] and yang_line[1] and yin_line[0] ? add_signal("limin", "黎明之星", 2, 3) : false

check_pattern1() =>
    if not is_bar_used(2) and not is_bar_used(1) and not is_bar_used(0)
        // 检测十字星
        is_doji = math.abs(close - open) <= (high - low) * doji_body_ratio and 
                 high > math.max(close, open) and 
                 low < math.min(close, open)
        
        // 检测平行十字星
        two_parallel_doji = is_doji[1] and is_doji[2] and 
                           math.max(high[1], high[2]) - math.min(low[1], low[2]) <= 
                           (high[2] - low[2]) * parallel_threshold
        
        // 检测强阳线
        is_strong_yang = yang_line and entity_length >= (high - low) * strong_body_ratio
        
        two_parallel_doji and is_strong_yang ? add_signal("pattern1", "双十字星+长阳", 2, 3) : false
    else
        false

check_pattern2() =>
    if not is_bar_used(2) and not is_bar_used(1) and not is_bar_used(0)
        // 检测十字星
        is_doji = math.abs(close - open) <= (high - low) * doji_body_ratio and 
                 high > math.max(close, open) and 
                 low < math.min(close, open)
        
        // 检测平行十字星
        two_parallel_doji = is_doji[1] and is_doji[2] and 
                           math.max(high[1], high[2]) - math.min(low[1], low[2]) <= 
                           (high[2] - low[2]) * parallel_threshold
        
        // 检测强阴线
        is_strong_yin = yin_line and 
                       entity_length >= (high - low) * strong_body_ratio
        
        two_parallel_doji and is_strong_yin ? add_signal("pattern2", "双十字星+长阴", 2, 3) : false
    else
        false

// ============ 主逻辑 ============
check_all_patterns() =>
    check_huanhun() or check_limin() or check_pattern1() or check_pattern2() or check_yin_to_yang() or check_yang_to_yin()

// 清理旧信号和检查模式
if barstate.isconfirmed
    clean_old_signals()
    check_all_patterns()
    
    // 定期清理used_bar_indices数组
    if bar_index - last_clean_bar > 500
        new_indices = array.new_int(0)
        for i = 0 to array.size(used_bar_indices) - 1
            used_bar = array.get(used_bar_indices, i)
            if bar_index - used_bar < history_size
                array.push(new_indices, used_bar)
        used_bar_indices := new_indices
        last_clean_bar := bar_index

// ============ 可视化 ============
barcolor(yang_line ? new_color(#00FF00, 80) : yin_line ? new_color(#FF0000, 80) : na)

// ============ 图表信息显示 ============
var table info_table = table.new(position.top_right, 1, 1, bgcolor=color.new(#1E1E1E, 90), border_width=2)

if barstate.islast
    table.cell(info_table, 0, 0, 
               text="K线组合策略 V12\n" + 
               "激活信号: " + str.tostring(array.size(signal_lines)) + 
               "\n历史大小: " + str.tostring(array.size(used_bar_indices)),
               text_color=color.white,
               text_size=size.small)

// 添加屏幕右下角信号统计
if barstate.islast
    // 构建统计文本
    info_text = "信号统计:\n" +
               "阴转阳: " + str.tostring(yin_to_yang_count) + "\n" +
               "阳转阴: " + str.tostring(yang_to_yin_count) + "\n" +
               "黄昏之星: " + str.tostring(huanhun_count) + "\n" +
               "黎明之星: " + str.tostring(limin_count) + "\n" +
               "双十字星+长阳: " + str.tostring(pattern1_count) + "\n" +
               "双十字星+长阴: " + str.tostring(pattern2_count)
    
    // 计算标签位置
    max_price = ta.highest(high, 100)
    label_y = max_price * 1.05
    
    label.new(x=bar_index, y=label_y,text=info_text,color=color.new(#1E1E1E, 90),textcolor=color.white,style=label.style_label_center,size=size.small,xloc=xloc.bar_index,yloc=yloc.price)

// 添加屏幕左上角总结信息
if barstate.islast
    total_signals = yin_to_yang_count + yang_to_yin_count + huanhun_count + 
                   limin_count + pattern1_count + pattern2_count
    summary_text = "信号总结:\n总信号数: " + str.tostring(total_signals) + 
                  "\n当前激活: " + str.tostring(array.size(signal_lines))
    
    label.new(x=bar_index[20], y=high[20] * 1.02,text=summary_text,color=color.new(#1E1E1E, 90),textcolor=color.white,style=label.style_label_left,size=size.small,xloc=xloc.bar_index,yloc=yloc.price)