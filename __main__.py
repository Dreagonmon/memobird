from memobird import MemobirdClient, Paper
import asyncio


async def _test():
    client = MemobirdClient()
    # client = MemobirdClient("客户端Session保存路径.json")
    
    async with client:
        # 如果当前保存的Session还有效，则无需登录
        if not client.is_logged_in:
            # print("使用密码登录")
            # await client.login("手机号", "密码")
            print("扫码登录")
            await client.login_with_qr()
        
        # 构造纸条对象
        paper = Paper()
        # paper = Paper(576) # 更高分辨率的咕咕机
        paper.append_text("Hello World~\n咕咕咕!")
        # 图片需要提前上传
        # src = await client.upload_image("图片路径.jpg")
        paper.append_image("https://cn.bing.com/th?id=OHR.DarkSkyAcadia_ZH-CN1827511700_1920x1200.jpg&rf=LaDigue_1920x1200.jpg")

        # 也可以自定义类继承PaperItem，然后添加到纸条对象
        # from memobird import PaperItemImage, PaperItemText
        # text = PaperItemText("Hello Dragon~\nThis is a new librery!")
        # img = PaperItemImage("https://cn.bing.com/th?id=OHR.DarkSkyAcadia_ZH-CN1827511700_1920x1200.jpg&rf=LaDigue_1920x1200.jpg")
        # paper.append(text)
        # paper.append(img)

        # 生成纸条预览，用于debug，可以省略这一步
        with open("preview.html", "w") as f:
            f.write(paper.get_preview_html())
        # 发送打印的内容，格式是html，但是对样式表的支持有限，需要更多的兼容性测试
        print("发送打印的内容")
        resp = await client.print_html(paper.get_html())
        # 选择其它设备进行打印，设备信息可以查看client.devices
        # resp = await client.print_html(paper.get_html(), 1)
        if resp:
            print("发送成功")
    # 对于长时间运行的脚本来说，要定期刷新Session，防止Session过期
    print("开始循环刷新以保留会话...")
    while True:
        await asyncio.sleep(5 * 60) # 这里间隔5分钟
        async with client:
            await client.update_info()
            print(client.is_logged_in)
            print(client.devices)

if __name__ == "__main__":
    asyncio.run(_test())
    pass