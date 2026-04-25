#pragma once
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

#include <functional>

#include "../Activity.h"

class HomeActivity final : public Activity {
  TaskHandle_t displayTaskHandle = nullptr;
  SemaphoreHandle_t renderingMutex = nullptr;
  int selectorIndex = 0;
  bool updateRequired = false;
  const std::function<void()> onReaderOpen;
  const std::function<void()> onSettingsOpen;
  const std::function<void()> onFileTransferOpen;
  // 新增：静态网址按钮的回调函数（与原有回调风格一致）
  const std::function<void()> onStaticUrlOpen;

  static void taskTrampoline(void* param);
  [[noreturn]] void displayTaskLoop();
  void render() const;

 public:
  // 新增：构造函数添加onStaticUrlOpen参数（放在最后，不影响原有调用）
  explicit HomeActivity(GfxRenderer& renderer, InputManager& inputManager, const std::function<void()>& onReaderOpen,
                        const std::function<void()>& onSettingsOpen, const std::function<void()>& onFileTransferOpen,
                        const std::function<void()>& onStaticUrlOpen)  // 新增参数
      : Activity("Home", renderer, inputManager),
        onReaderOpen(onReaderOpen),
        onSettingsOpen(onSettingsOpen),
        onFileTransferOpen(onFileTransferOpen),
        onStaticUrlOpen(onStaticUrlOpen) {}  // 初始化新增回调
  void onEnter() override;
  void onExit() override;
  void loop() override;
};