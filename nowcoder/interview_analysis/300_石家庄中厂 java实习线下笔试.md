[查看原文](https://www.nowcoder.com/feed/main/detail/4ddd39bef74c43409bd6b4e376ac698b)

根据您提供的面试记录，以下是整理出的所有面试问题：

### 后端问题

1.  **Java String对象创建问题：**
    *   代码如下：
        ```java
        String s="ss"
        String a ="aa"
        String b = s+a
        ```
    *   问：创建了几个对象？

2.  **基本数据类型赋值与值传递：**
    *   代码如下：
        ```java
        int a =10
        int b=a
        b=20
        ```
    *   问：求a=？，为什么？

3.  **String引用赋值问题：**
    *   代码如下：
        ```java
        String a ="ss"
        String b=a
        b = "aa"
        ```
    *   问：a=？，为什么？

4.  **对象引用赋值问题：**
    *   代码逻辑：
        ```java
        p1 = new Person; p1.Name("张三")
        p2 = new Person
        p1 = p2
        p2.Name("王五")
        ```
    *   问：p1的name是什么？

5.  **方法参数引用传递问题（代码逻辑分析）：**
    *   代码逻辑：
        ```java
        class student {
            void fuc（A a） {
                a.Name = "王五"
                a = new Student
                a.Name = "李四"
                // 这里问：a的name是什么？
            }
        }
        
        // 外部调用
        a1 = new student
        a1.Name = "李四"
        fuc(a1)
        ```
    *   问：
        1.  在方法 `fuc` 内部最后一行，a 的 name 是什么？
        2.  调用 `fuc(a1)` 后，外部 `a1` 的 name 是什么？

6.  **数据类型区别：**
    *   问：BigDecimal、float、double 的区别？

7.  **多线程基础：**
    *   问：开启新线程的方法有哪些？

8.  **Spring注解：**
    *   问：@Lazy 是什么？

9.  **线程池对比：**
    *   问：new Thread 与 Executor 线程池框架的区别？

10. **线程本地变量：**
    *   问：ThreadLocal 是什么？

11. **Spring生命周期注解：**
    *   问：@PostConstruct 和 @PreDestroy 的区别？

12. **SpringBoot嵌入式容器：**
    *   问：SpringBoot 为什么不用配置 tomcat？

13. **Spring Bean加载/查找机制：**
    *   问：有什么方法能让 bean 创建时先去 IOC 容器找相同名字的 bean，如果没有再按名称创建？

14. **异常处理机制：**
    *   问：在 try catch 中，finally（原文记为final）一定会执行吗？在 return 前还是后执行？

15. **全局异常处理：**
    *   问：怎么处理全局异常？

16. **SpringBoot配置文件：**
    *   问：SpringBoot 的配置文件有哪几种？

17. **SpringBoot配置加载：**
    *   问：如何让 SpringBoot 启动时就加载其它配置？

18. **错误日志分析：**
    *   问：给了一条错误信息 `xxx map xxx “xxController” not methed`（原文拼写），分析原因和解决方案。

### 前端问题

19. **Vue响应式原理：**
    *   问：Vue2 和 Vue3 的响应式布局（原理）？

20. **路由实现：**
    *   问：如何实现动态路由？