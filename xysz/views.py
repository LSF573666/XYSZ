# from django.http import JsonResponse
# import pandas as pd
# from xysz.core.wsbiget_1m import start_multiple_subscriptions
# from xysz.main_biget import cof_main
# from xysz.tasks import FB_strategy, KC_strategy

# def FB_view(request):
#     middle_his_data, slow_his_data = cof_main()
#     strategy_flag = True  # 初始状态为 True，允许策略执行
#     ws, data_queue = start_multiple_subscriptions()
#     while strategy_flag:
#         if not data_queue.empty():
#             # 有数据进来，更新时间戳
#             strategy_flag = False
#             kline_data = data_queue.get_nowait()
#             kline_data_df = pd.DataFrame([kline_data])
#             ws_type = kline_data_df['symbol'][0]
#             ws_type = ws_type.replace("USDT", "")
#             print(kline_data_df['symbol'][0])
#             FB_strategy.delay(ws_type, middle_his_data[ws_type].to_dict("records"), slow_his_data[ws_type].to_dict("records"))

#     return JsonResponse({"status": "task started"})


# def KC_view(request):
#     KC_strategy.delay()  # 触发异步任务
#     return JsonResponse({"status": "task started"})
