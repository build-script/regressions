// Headless Vulkan compute program of the spike: doubles 16 numbers on the GPU, no window.
// With --misuse it leaks a buffer at vkDestroyDevice on purpose, so the validation layers report it.
#include <vulkan/vulkan.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

// SPIR-V of double.comp, from glslc -mfmt=c
static const uint32_t shader_code[] =
#include "double.spv.h"
    ;

static const uint32_t COUNT = 16;

static const char* result_name(VkResult r) {
    switch (r) {
#define NAME(x) \
    case x:     \
        return #x;
        NAME(VK_SUCCESS)
        NAME(VK_NOT_READY)
        NAME(VK_TIMEOUT)
        NAME(VK_INCOMPLETE)
        NAME(VK_ERROR_OUT_OF_HOST_MEMORY)
        NAME(VK_ERROR_OUT_OF_DEVICE_MEMORY)
        NAME(VK_ERROR_INITIALIZATION_FAILED)
        NAME(VK_ERROR_DEVICE_LOST)
        NAME(VK_ERROR_MEMORY_MAP_FAILED)
        NAME(VK_ERROR_LAYER_NOT_PRESENT)
        NAME(VK_ERROR_EXTENSION_NOT_PRESENT)
        NAME(VK_ERROR_FEATURE_NOT_PRESENT)
        NAME(VK_ERROR_INCOMPATIBLE_DRIVER)
        NAME(VK_ERROR_TOO_MANY_OBJECTS)
        NAME(VK_ERROR_FORMAT_NOT_SUPPORTED)
        NAME(VK_ERROR_UNKNOWN)
#undef NAME
    default:
        return "unknown VkResult";
    }
}

#define CHECK(call)                                                                       \
    do {                                                                                  \
        VkResult r_ = (call);                                                             \
        if (r_ != VK_SUCCESS) {                                                           \
            std::fprintf(stderr, "%s failed: %s (%d)\n", #call, result_name(r_), (int)r_); \
            std::exit(1);                                                                 \
        }                                                                                 \
    } while (0)

static void print_version(const char* what, uint32_t v) {
    std::printf("%s %u.%u.%u\n", what, VK_API_VERSION_MAJOR(v), VK_API_VERSION_MINOR(v), VK_API_VERSION_PATCH(v));
}

int main(int argc, char** argv) {
    bool misuse = argc > 1 && std::strcmp(argv[1], "--misuse") == 0;
    std::setvbuf(stdout, nullptr, _IONBF, 0);

    uint32_t loader_version = VK_API_VERSION_1_0;
    vkEnumerateInstanceVersion(&loader_version);
    print_version("loader:", loader_version);

    uint32_t count = 0;
    vkEnumerateInstanceLayerProperties(&count, nullptr);
    std::vector<VkLayerProperties> layers(count);
    vkEnumerateInstanceLayerProperties(&count, layers.data());
    std::printf("instance layers: %u\n", count);
    for (auto& layer : layers) std::printf("  %s\n", layer.layerName);

    count = 0;
    vkEnumerateInstanceExtensionProperties(nullptr, &count, nullptr);
    std::vector<VkExtensionProperties> extensions(count);
    vkEnumerateInstanceExtensionProperties(nullptr, &count, extensions.data());
    bool portability = false;
    for (auto& e : extensions)
        if (std::strcmp(e.extensionName, VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME) == 0) portability = true;

    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.pApplicationName = "vulkan-spike";
    app.apiVersion = VK_API_VERSION_1_1;
    const char* instance_extensions[] = {VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME};
    VkInstanceCreateInfo instance_info{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    instance_info.pApplicationInfo = &app;
    if (portability) {
        // MoltenVK is a portability driver: the loader shows it only with this extension
        instance_info.flags = VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR;
        instance_info.enabledExtensionCount = 1;
        instance_info.ppEnabledExtensionNames = instance_extensions;
    }
    VkInstance instance;
    VkResult r = vkCreateInstance(&instance_info, nullptr, &instance);
    if (r != VK_SUCCESS) {
        std::fprintf(stderr, "vkCreateInstance failed: %s (%d)\n", result_name(r), (int)r);
        return 2;
    }

    count = 0;
    CHECK(vkEnumeratePhysicalDevices(instance, &count, nullptr));
    if (count == 0) {
        std::fprintf(stderr, "no Vulkan device: vkEnumeratePhysicalDevices found none\n");
        return 3;
    }
    std::vector<VkPhysicalDevice> devices(count);
    CHECK(vkEnumeratePhysicalDevices(instance, &count, devices.data()));

    VkPhysicalDevice physical = VK_NULL_HANDLE;
    uint32_t family = 0;
    for (auto device : devices) {
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties(device, &props);
        std::printf("device: %s (type %d)\n", props.deviceName, (int)props.deviceType);
        print_version("  api:", props.apiVersion);
        if (props.apiVersion >= VK_API_VERSION_1_2) {
            VkPhysicalDeviceDriverProperties driver{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
            VkPhysicalDeviceProperties2 props2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &driver};
            vkGetPhysicalDeviceProperties2(device, &props2);
            std::printf("  driver: %s, %s\n", driver.driverName, driver.driverInfo);
        }
        uint32_t families = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(device, &families, nullptr);
        std::vector<VkQueueFamilyProperties> queue_families(families);
        vkGetPhysicalDeviceQueueFamilyProperties(device, &families, queue_families.data());
        for (uint32_t i = 0; i < families && physical == VK_NULL_HANDLE; i++) {
            if (queue_families[i].queueFlags & VK_QUEUE_COMPUTE_BIT) {
                physical = device;
                family = i;
            }
        }
    }
    if (physical == VK_NULL_HANDLE) {
        std::fprintf(stderr, "no device with a compute queue\n");
        return 3;
    }

    // a portability driver wants VK_KHR_portability_subset enabled when it offers it
    count = 0;
    vkEnumerateDeviceExtensionProperties(physical, nullptr, &count, nullptr);
    std::vector<VkExtensionProperties> device_extensions(count);
    vkEnumerateDeviceExtensionProperties(physical, nullptr, &count, device_extensions.data());
    std::vector<const char*> enabled;
    for (auto& e : device_extensions)
        if (std::strcmp(e.extensionName, "VK_KHR_portability_subset") == 0) enabled.push_back("VK_KHR_portability_subset");

    float priority = 1.0f;
    VkDeviceQueueCreateInfo queue_info{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    queue_info.queueFamilyIndex = family;
    queue_info.queueCount = 1;
    queue_info.pQueuePriorities = &priority;
    VkDeviceCreateInfo device_info{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    device_info.queueCreateInfoCount = 1;
    device_info.pQueueCreateInfos = &queue_info;
    device_info.enabledExtensionCount = (uint32_t)enabled.size();
    device_info.ppEnabledExtensionNames = enabled.data();
    VkDevice device;
    CHECK(vkCreateDevice(physical, &device_info, nullptr, &device));
    VkQueue queue;
    vkGetDeviceQueue(device, family, 0, &queue);

    VkBufferCreateInfo buffer_info{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    buffer_info.size = COUNT * sizeof(uint32_t);
    buffer_info.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT;
    buffer_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    VkBuffer buffer;
    CHECK(vkCreateBuffer(device, &buffer_info, nullptr, &buffer));

    VkMemoryRequirements requirements;
    vkGetBufferMemoryRequirements(device, buffer, &requirements);
    VkPhysicalDeviceMemoryProperties memory_props;
    vkGetPhysicalDeviceMemoryProperties(physical, &memory_props);
    const VkMemoryPropertyFlags wanted = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
    uint32_t type = UINT32_MAX;
    for (uint32_t i = 0; i < memory_props.memoryTypeCount && type == UINT32_MAX; i++)
        if ((requirements.memoryTypeBits & (1u << i)) && (memory_props.memoryTypes[i].propertyFlags & wanted) == wanted)
            type = i;
    if (type == UINT32_MAX) {
        std::fprintf(stderr, "no host visible, coherent memory\n");
        return 1;
    }
    VkMemoryAllocateInfo allocate_info{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    allocate_info.allocationSize = requirements.size;
    allocate_info.memoryTypeIndex = type;
    VkDeviceMemory memory;
    CHECK(vkAllocateMemory(device, &allocate_info, nullptr, &memory));
    CHECK(vkBindBufferMemory(device, buffer, memory, 0));
    uint32_t* values = nullptr;
    CHECK(vkMapMemory(device, memory, 0, buffer_info.size, 0, (void**)&values));
    for (uint32_t i = 0; i < COUNT; i++) values[i] = i + 1;

    VkDescriptorSetLayoutBinding binding{};
    binding.binding = 0;
    binding.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    binding.descriptorCount = 1;
    binding.stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    VkDescriptorSetLayoutCreateInfo set_layout_info{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    set_layout_info.bindingCount = 1;
    set_layout_info.pBindings = &binding;
    VkDescriptorSetLayout set_layout;
    CHECK(vkCreateDescriptorSetLayout(device, &set_layout_info, nullptr, &set_layout));

    VkPipelineLayoutCreateInfo pipeline_layout_info{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    pipeline_layout_info.setLayoutCount = 1;
    pipeline_layout_info.pSetLayouts = &set_layout;
    VkPipelineLayout pipeline_layout;
    CHECK(vkCreatePipelineLayout(device, &pipeline_layout_info, nullptr, &pipeline_layout));

    VkShaderModuleCreateInfo module_info{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    module_info.codeSize = sizeof(shader_code);
    module_info.pCode = shader_code;
    VkShaderModule module;
    CHECK(vkCreateShaderModule(device, &module_info, nullptr, &module));

    VkComputePipelineCreateInfo pipeline_info{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
    pipeline_info.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    pipeline_info.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    pipeline_info.stage.module = module;
    pipeline_info.stage.pName = "main";
    pipeline_info.layout = pipeline_layout;
    VkPipeline pipeline;
    CHECK(vkCreateComputePipelines(device, VK_NULL_HANDLE, 1, &pipeline_info, nullptr, &pipeline));

    VkDescriptorPoolSize pool_size{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1};
    VkDescriptorPoolCreateInfo pool_info{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
    pool_info.maxSets = 1;
    pool_info.poolSizeCount = 1;
    pool_info.pPoolSizes = &pool_size;
    VkDescriptorPool pool;
    CHECK(vkCreateDescriptorPool(device, &pool_info, nullptr, &pool));
    VkDescriptorSetAllocateInfo set_info{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
    set_info.descriptorPool = pool;
    set_info.descriptorSetCount = 1;
    set_info.pSetLayouts = &set_layout;
    VkDescriptorSet set;
    CHECK(vkAllocateDescriptorSets(device, &set_info, &set));
    VkDescriptorBufferInfo described{buffer, 0, VK_WHOLE_SIZE};
    VkWriteDescriptorSet write{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
    write.dstSet = set;
    write.dstBinding = 0;
    write.descriptorCount = 1;
    write.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    write.pBufferInfo = &described;
    vkUpdateDescriptorSets(device, 1, &write, 0, nullptr);

    VkCommandPoolCreateInfo command_pool_info{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    command_pool_info.queueFamilyIndex = family;
    VkCommandPool command_pool;
    CHECK(vkCreateCommandPool(device, &command_pool_info, nullptr, &command_pool));
    VkCommandBufferAllocateInfo command_info{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    command_info.commandPool = command_pool;
    command_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    command_info.commandBufferCount = 1;
    VkCommandBuffer commands;
    CHECK(vkAllocateCommandBuffers(device, &command_info, &commands));

    VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    CHECK(vkBeginCommandBuffer(commands, &begin));
    vkCmdBindPipeline(commands, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline);
    vkCmdBindDescriptorSets(commands, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline_layout, 0, 1, &set, 0, nullptr);
    vkCmdDispatch(commands, 1, 1, 1);
    VkMemoryBarrier barrier{VK_STRUCTURE_TYPE_MEMORY_BARRIER};
    barrier.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT;
    barrier.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
    vkCmdPipelineBarrier(commands, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_HOST_BIT, 0, 1, &barrier,
                         0, nullptr, 0, nullptr);
    CHECK(vkEndCommandBuffer(commands));

    VkFenceCreateInfo fence_info{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    VkFence fence;
    CHECK(vkCreateFence(device, &fence_info, nullptr, &fence));
    VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
    submit.commandBufferCount = 1;
    submit.pCommandBuffers = &commands;
    CHECK(vkQueueSubmit(queue, 1, &submit, fence));
    CHECK(vkWaitForFences(device, 1, &fence, VK_TRUE, 10ull * 1000 * 1000 * 1000));

    bool ok = true;
    std::printf("result:");
    for (uint32_t i = 0; i < COUNT; i++) {
        std::printf(" %u", values[i]);
        if (values[i] != 2 * (i + 1)) ok = false;
    }
    std::printf("\n%s\n", ok ? "ok: every number doubled" : "WRONG RESULT");

    vkDestroyFence(device, fence, nullptr);
    vkDestroyCommandPool(device, command_pool, nullptr);
    vkDestroyDescriptorPool(device, pool, nullptr);
    vkDestroyPipeline(device, pipeline, nullptr);
    vkDestroyShaderModule(device, module, nullptr);
    vkDestroyPipelineLayout(device, pipeline_layout, nullptr);
    vkDestroyDescriptorSetLayout(device, set_layout, nullptr);
    vkUnmapMemory(device, memory);
    if (misuse) {
        std::printf("misuse: the buffer stays alive past vkDestroyDevice\n");
    } else {
        vkDestroyBuffer(device, buffer, nullptr);
    }
    vkFreeMemory(device, memory, nullptr);
    vkDestroyDevice(device, nullptr);
    vkDestroyInstance(instance, nullptr);
    return ok ? 0 : 4;
}
