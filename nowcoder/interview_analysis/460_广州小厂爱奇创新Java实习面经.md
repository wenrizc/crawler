[查看原文](https://www.nowcoder.com/feed/main/detail/2d76de13368341d7882b259dd063c332)

根据提供的面试记录，以下是解析出的所有面试问题，分为笔试题目和面试题目两部分：

### 一、 笔试题目
1. Exception和Error都是继承Throwable，有什么区别？
2. 线程的Thread.sleep(0)什么意义？有什么替代方法？
3. 线程池的意义是什么？你会怎么创建线程池（使用Executor有什么缺陷）？
4. shutdown()之后，线程池已经提交的任务会被执行吗？
5. Java的设计模式有哪些？
6. UUID是32位的16进制编码怎么转换成Base64？写出计算方式。
7. Java的饿汉式和懒汉式有什么区别？
8. 对Spring的IOC的理解？
9. BeanFactory和ApplicationContext这两个Spring的IOC容器的区别？
10. 算法题：LeetCode的搜索二维矩阵II（Search a 2D Matrix II）。

### 二、 面试题目
1. 手撕switch语句怎么写？（考察跳出语句break等）
2. 手撕SQL：有user和phone两张表，需要查询phone表中有一条及以上记录的user。
3. 场景题：有a、b、c三个任务，c要等待a、b完成后再执行，问怎么实现？
4. 要实现每月签到功能要怎么实现？
5. （追问）int要存储到哪里去？
6. （追问）redis里存储的是什么数据？
7. es的分词器相关：怎么保证输入的歌曲在es中能准确搜索出来？（例如：假如歌手名字叫“一二”，会不会被分成“一”、“二”？）